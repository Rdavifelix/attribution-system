"""
Motor de cruzamento: Lead ↔ Anúncio.

Roda após cada ingestão (planilha ou GHL).
Para cada lead sem match, tenta os métodos em ordem decrescente de confiança:

  1. fb_ad_id direto (Alta)      — vem do GHL via UTM macro {{ad.id}}
  2. utm_content contém ad_id    (Alta)   — convenção de nomenclatura
  3. utm_campaign ≈ campaign_name (Baixa) — fallback de texto

Resultado:
  - INSERT em lead_ad_match (1 registro por lead — o melhor match)
  - Leads sem match ficam sem registro → aparecem no painel de qualidade
"""
from __future__ import annotations
import logging
import re

from backend.db.client import db

logger = logging.getLogger(__name__)


def _extract_ad_id_from_utm_content(utm_content: str | None) -> str | None:
    """
    Tenta extrair um ad_id numérico do utm_content.
    Padrão esperado: algo como 'PAA_ad_120207846123_awareness'
    ou simplesmente o ad_id puro.
    """
    if not utm_content:
        return None
    # Procura sequência de 15+ dígitos (IDs do Meta são longos)
    m = re.search(r"\b(\d{15,})\b", utm_content)
    return m.group(1) if m else None


def _fuzzy_campaign_match(utm_campaign: str | None, campaign_names: list[str]) -> str | None:
    """
    Correspondência simples: verifica se o utm_campaign está contido
    no campaign_name ou vice-versa (case-insensitive).
    Retorna o campaign_name correspondente ou None.
    """
    if not utm_campaign:
        return None
    uc = utm_campaign.strip().lower()
    for cn in campaign_names:
        if cn and (uc in cn.lower() or cn.lower() in uc):
            return cn
    return None


def _get_ad_ids_for_campaign(campaign_name: str, funnel_id: int) -> list[str]:
    """Retorna todos os ad_ids de uma campanha (para match de campanha)."""
    res = (
        db.table("ad_performance")
        .select("ad_id")
        .eq("funnel_id", funnel_id)
        .eq("campaign_name", campaign_name)
        .execute()
    )
    return list({r["ad_id"] for r in (res.data or [])})


def run_match(funnel_id: int | None = None) -> dict:
    """
    Processa todos os leads sem match no funil.
    Retorna contadores de resultado.
    """
    from backend.config.settings import settings
    funnel_id = funnel_id or settings.default_funnel_id

    # Leads sem match
    matched_ids_res = db.table("lead_ad_match").select("lead_id").execute()
    matched_ids = {r["lead_id"] for r in (matched_ids_res.data or [])}

    leads_res = (
        db.table("leads")
        .select("id, fb_ad_id, utm_content, utm_campaign, funnel_id")
        .eq("funnel_id", funnel_id)
        .execute()
    )
    leads = [l for l in (leads_res.data or []) if l["id"] not in matched_ids]
    logger.info(f"[match] {len(leads)} leads sem match para processar")

    # Cache de campaign_names disponíveis no Meta
    camps_res = (
        db.table("ad_performance")
        .select("campaign_name")
        .eq("funnel_id", funnel_id)
        .execute()
    )
    campaign_names = list({r["campaign_name"] for r in (camps_res.data or []) if r["campaign_name"]})

    stats = {"alta": 0, "media": 0, "baixa": 0, "sem_match": 0}
    inserts = []

    for lead in leads:
        match_record = None

        # ── Método 1: fb_ad_id direto ────────────────────────────
        if lead.get("fb_ad_id"):
            match_record = {
                "lead_id":         lead["id"],
                "ad_id":           lead["fb_ad_id"],
                "match_method":    "fb_ad_id",
                "match_confidence":"alta",
            }
            stats["alta"] += 1

        # ── Método 2: ad_id dentro do utm_content ────────────────
        if not match_record:
            extracted = _extract_ad_id_from_utm_content(lead.get("utm_content"))
            if extracted:
                # Valida que esse ad_id existe no banco
                exists_res = (
                    db.table("ad_performance")
                    .select("ad_id")
                    .eq("funnel_id", funnel_id)
                    .eq("ad_id", extracted)
                    .limit(1)
                    .execute()
                )
                if exists_res.data:
                    match_record = {
                        "lead_id":         lead["id"],
                        "ad_id":           extracted,
                        "match_method":    "utm_content",
                        "match_confidence":"alta",
                    }
                    stats["alta"] += 1

        # ── Método 3: utm_campaign ≈ campaign_name ───────────────
        if not match_record:
            matched_campaign = _fuzzy_campaign_match(lead.get("utm_campaign"), campaign_names)
            if matched_campaign:
                ad_ids = _get_ad_ids_for_campaign(matched_campaign, funnel_id)
                if ad_ids:
                    # Se há múltiplos anúncios na campanha, não podemos saber qual.
                    # Usamos o mais recente (maior gasto no período mais recente).
                    best_res = (
                        db.table("ad_performance")
                        .select("ad_id, spend")
                        .eq("funnel_id", funnel_id)
                        .eq("campaign_name", matched_campaign)
                        .order("spend", desc=True)
                        .limit(1)
                        .execute()
                    )
                    if best_res.data:
                        match_record = {
                            "lead_id":         lead["id"],
                            "ad_id":           best_res.data[0]["ad_id"],
                            "match_method":    "utm_campaign",
                            "match_confidence":"baixa",
                        }
                        stats["baixa"] += 1

        if match_record:
            inserts.append(match_record)
        else:
            stats["sem_match"] += 1

    # Bulk insert
    if inserts:
        db.table("lead_ad_match").upsert(inserts, on_conflict="lead_id").execute()

    logger.info(f"[match] Concluído — {stats}")
    return stats
