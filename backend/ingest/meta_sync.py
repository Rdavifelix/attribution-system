"""
Ingestão do Meta Ads Insights → banco.

Estratégia:
- Nível: ad (granularidade máxima para atribuição)
- time_increment: 1 (um registro por dia por anúncio)
- Re-puxa sempre os últimos 7 dias (Meta atualiza conversões com atraso)
- Requisições assíncronas (async report job) para contas grandes
- UPSERT com UNIQUE(funnel_id, data, ad_id)
"""
from __future__ import annotations
import logging
import time
from datetime import date, timedelta

import httpx

from backend.config.settings import settings
from backend.db.client import db

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.facebook.com"


def _get_token() -> str:
    """Gets Meta token: first tries DB (OAuth token), then falls back to env var."""
    # Try DB first (OAuth flow token)
    try:
        res = db.table("system_settings").select("value").eq("key", "meta_access_token").execute()
        if res.data and res.data[0]["value"]:
            return res.data[0]["value"]
    except Exception:
        pass
    # Fall back to env var (System User Token)
    if settings.meta_system_user_token:
        return settings.meta_system_user_token
    raise ValueError("Meta token não configurado. Acesse /auth/meta para conectar.")

FIELDS = ",".join([
    "campaign_id",
    "campaign_name",
    "adset_id",
    "adset_name",
    "ad_id",
    "ad_name",
    "spend",
    "impressions",
    "clicks",
    "ctr",
    "cpc",
    "cpm",
    "actions",
])


def _headers() -> dict:
    return {"Content-Type": "application/json"}


def _params_base() -> dict:
    return {"access_token": _get_token()}


def _date_range(days_back: int = 7) -> tuple[str, str]:
    end   = date.today() - timedelta(days=1)
    start = end - timedelta(days=days_back - 1)
    return start.isoformat(), end.isoformat()


def _launch_async_report(ad_account_id: str, since: str, until: str) -> str:
    """Cria um async report job no Meta e retorna o report_run_id."""
    url = f"{BASE_URL}/{settings.meta_api_version}/act_{ad_account_id}/insights"
    params = {
        **_params_base(),
        "fields":         FIELDS,
        "level":          "ad",
        "time_increment": "1",
        "time_range":     f'{{"since":"{since}","until":"{until}"}}',
    }
    resp = httpx.post(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    report_run_id = data.get("report_run_id")
    if not report_run_id:
        raise ValueError(f"Meta não retornou report_run_id: {data}")
    logger.info(f"[meta_sync] Report job criado: {report_run_id}")
    return report_run_id


def _wait_for_report(report_run_id: str, max_wait: int = 300) -> None:
    """Aguarda o report job terminar (polling com backoff)."""
    url = f"{BASE_URL}/{settings.meta_api_version}/{report_run_id}"
    waited = 0
    interval = 10
    while waited < max_wait:
        resp = httpx.get(url, params=_params_base(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pct = data.get("async_percent_completion", 0)
        status = data.get("async_status", "")
        logger.info(f"[meta_sync] Report status: {status} ({pct}%)")
        if status == "Job Completed":
            return
        if status in ("Job Failed", "Job Skipped"):
            raise RuntimeError(f"Report job falhou: {data}")
        time.sleep(interval)
        waited += interval
    raise TimeoutError(f"Report job não terminou em {max_wait}s")


def _fetch_report_results(report_run_id: str) -> list[dict]:
    """Busca os dados do report (paginação automática)."""
    url = f"{BASE_URL}/{settings.meta_api_version}/{report_run_id}/insights"
    params = {**_params_base(), "limit": 500}
    results = []

    while True:
        resp = httpx.get(url, params=params, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        results.extend(body.get("data", []))

        # Paginação
        next_cursor = body.get("paging", {}).get("cursors", {}).get("after")
        if not next_cursor or not body.get("data"):
            break
        params["after"] = next_cursor

    return results


def _parse_row(row: dict, funnel_id: int) -> dict:
    """Converte um registro da API do Meta para o schema do banco."""

    def safe_float(v):
        try:
            return float(v) if v else None
        except (TypeError, ValueError):
            return None

    def safe_int(v):
        try:
            return int(v) if v else None
        except (TypeError, ValueError):
            return None

    return {
        "funnel_id":     funnel_id,
        "data":          row.get("date_start"),
        "campaign_id":   row.get("campaign_id"),
        "campaign_name": row.get("campaign_name"),
        "adset_id":      row.get("adset_id"),
        "adset_name":    row.get("adset_name"),
        "ad_id":         row.get("ad_id"),
        "ad_name":       row.get("ad_name"),
        "spend":         safe_float(row.get("spend")),
        "impressions":   safe_int(row.get("impressions")),
        "clicks":        safe_int(row.get("clicks")),
        "ctr":           safe_float(row.get("ctr")),
        "cpc":           safe_float(row.get("cpc")),
        "cpm":           safe_float(row.get("cpm")),
        "actions":       row.get("actions"),  # lista de {action_type, value}
    }


def sync_meta(
    ad_account_id: str | None = None,
    funnel_id: int | None = None,
    days_back: int = 7,
) -> dict:
    """
    Ponto de entrada principal.
    Retorna resumo com contadores.
    """
    account = ad_account_id or settings.meta_ad_account_id
    funnel  = funnel_id     or settings.default_funnel_id

    if not account:
        logger.warning("[meta_sync] META_AD_ACCOUNT_ID não configurado — pulando")
        return {"status": "skipped", "reason": "no_account_id"}

    since, until = _date_range(days_back)
    logger.info(f"[meta_sync] Sincronizando {since} → {until} | conta act_{account}")

    try:
        # 1. Lança job assíncrono
        run_id = _launch_async_report(account, since, until)

        # 2. Aguarda conclusão
        _wait_for_report(run_id)

        # 3. Busca resultados
        rows = _fetch_report_results(run_id)
        logger.info(f"[meta_sync] {len(rows)} registros recebidos")

        # 4. Upsert no banco
        records = [_parse_row(r, funnel) for r in rows if r.get("ad_id")]
        if records:
            db.table("ad_performance").upsert(
                records,
                on_conflict="funnel_id,data,ad_id"
            ).execute()

        return {"status": "ok", "registros": len(records), "periodo": f"{since}/{until}"}

    except Exception as exc:
        logger.error(f"[meta_sync] Erro: {exc}", exc_info=True)
        return {"status": "error", "error": str(exc)}
