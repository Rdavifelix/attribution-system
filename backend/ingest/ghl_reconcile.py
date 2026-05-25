"""
Job de reconciliação diária do GHL.

Busca contatos atualizados nas últimas 72h que tenham a tag do funil,
e faz UPSERT dos dados de atribuição — rede de segurança caso um webhook
tenha falhado ou chegado fora de ordem.

Usa a API v2 do GHL (Private Integration Token).
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

import httpx

from backend.config.settings import settings
from backend.db.client import db
from backend.engine.normalizer import normalize_email, normalize_phone
from backend.ingest.ghl_webhook import _extract_utm_fields

logger = logging.getLogger(__name__)

GHL_API_BASE = "https://services.leadconnectorhq.com"


def _ghl_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.ghl_private_token}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
    }


def _fetch_contacts_page(location_id: str, tag: str, updated_after: str, cursor: str | None) -> dict:
    """Busca uma página de contatos com a tag e atualizados após a data."""
    params = {
        "locationId": location_id,
        "tags": tag,
        "dateUpdated": updated_after,
        "limit": 100,
    }
    if cursor:
        params["startAfter"] = cursor
        params["startAfterId"] = cursor

    resp = httpx.get(
        f"{GHL_API_BASE}/contacts/",
        headers=_ghl_headers(),
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def reconcile_ghl(
    location_id: str | None = None,
    tag: str | None = None,
    funnel_id: int | None = None,
    hours_back: int = 72,
) -> dict:
    """
    Reconcilia contatos do GHL atualizados nas últimas `hours_back` horas.
    """
    location_id = location_id or settings.ghl_location_id
    tag         = tag         or settings.ghl_funnel_tag
    funnel_id   = funnel_id   or settings.default_funnel_id

    if not location_id or not settings.ghl_private_token:
        logger.warning("[ghl_reconcile] GHL não configurado — pulando")
        return {"status": "skipped"}

    updated_after = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info(f"[ghl_reconcile] Buscando contatos atualizados desde {updated_after}")

    stats = {"processados": 0, "erros": 0}
    cursor = None

    while True:
        try:
            page = _fetch_contacts_page(location_id, tag, updated_after, cursor)
        except httpx.HTTPError as exc:
            logger.error(f"[ghl_reconcile] Erro na API GHL: {exc}")
            break

        contacts = page.get("contacts", [])
        if not contacts:
            break

        for contact in contacts:
            try:
                ghl_contact_id = contact.get("id")
                email_n   = normalize_email(contact.get("email"))
                telefone_n= normalize_phone(contact.get("phone"))
                utm_fields= _extract_utm_fields(contact)

                lead_data = {
                    "funnel_id":      funnel_id,
                    "ghl_contact_id": ghl_contact_id,
                    "email_norm":     email_n,
                    "telefone_norm":  telefone_n,
                    "nome":           contact.get("name"),
                    "raw_ghl":        contact,
                    "updated_at":     datetime.utcnow().isoformat(),
                    **{k: v for k, v in utm_fields.items() if v is not None},
                }

                # UPSERT por ghl_contact_id
                db.table("leads").upsert(
                    {**lead_data, "origem_registro": "ghl"},
                    on_conflict="ghl_contact_id",
                    # Não sobrescreve campos de qualificação da planilha
                    returning="minimal",
                ).execute()

                stats["processados"] += 1
            except Exception as exc:
                logger.error(f"[ghl_reconcile] Erro no contato {contact.get('id')}: {exc}")
                stats["erros"] += 1

        # Paginação
        meta = page.get("meta", {})
        cursor = meta.get("nextPageUrl")  # ou o campo correto de cursor do GHL v2
        total = meta.get("total", 0)
        if stats["processados"] >= total or not cursor:
            break

    logger.info(f"[ghl_reconcile] Concluído — {stats}")
    return stats
