"""
Endpoint FastAPI para receber webhooks do GoHighLevel.

O GHL dispara este webhook via Workflow quando um contato recebe a tag do funil.
Aqui extraímos APENAS os dados de atribuição (UTMs, fb_ad_id, fbclid).
Os dados de funil (calls, vendas) continuam vindo da planilha.

Endpoint: POST /ingest/ghl?funnel_id=<id>
"""
from __future__ import annotations
import logging
from datetime import datetime

from fastapi import APIRouter, Query, Request, HTTPException

from backend.config.settings import settings
from backend.db.client import db
from backend.engine.normalizer import normalize_email, normalize_phone
from backend.engine.match import run_match

logger = logging.getLogger(__name__)
router = APIRouter()


def _extract_utm_fields(body: dict) -> dict:
    """
    Extrai campos de atribuição do payload do GHL.
    O GHL pode enviar UTMs de formas diferentes dependendo da versão do Workflow.
    """
    attr = body.get("attributionSource") or body.get("attribution_source") or {}

    return {
        "utm_source":    body.get("utm_source")   or attr.get("utm_source"),
        "utm_medium":    body.get("utm_medium")   or attr.get("utm_medium"),
        "utm_campaign":  body.get("utm_campaign") or attr.get("utm_campaign"),
        "utm_content":   body.get("utm_content")  or attr.get("utm_content"),
        "utm_term":      body.get("utm_term")      or attr.get("utm_term"),
        "fbclid":        body.get("fbclid")        or attr.get("fbclid"),
        # O macro {{ad.id}} do Meta deve estar mapeado para um Custom Field 'fb_ad_id'
        "fb_ad_id":      body.get("fb_ad_id")     or body.get("customData", {}).get("fb_ad_id"),
        "fb_campaign_id":body.get("fb_campaign_id") or body.get("customData", {}).get("fb_campaign_id"),
        "fb_adset_id":   body.get("fb_adset_id")  or body.get("customData", {}).get("fb_adset_id"),
        "attribution_first": body.get("attribution_first") or attr,
        "attribution_last":  body.get("attribution_last"),
    }


@router.post("/ghl")
async def ingest_ghl(
    request: Request,
    funnel_id: int = Query(default=None),
):
    # Validação de secret (opcional)
    secret = settings.webhook_secret
    if secret and request.headers.get("x-webhook-secret") != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    funnel_id = funnel_id or settings.default_funnel_id

    # GHL envia array com um objeto ou objeto direto
    raw = await request.json()
    body = raw[0] if isinstance(raw, list) else raw
    body = body.get("body") or body

    ghl_contact_id = body.get("contact_id") or body.get("id")
    if not ghl_contact_id:
        logger.warning("[ghl_webhook] Payload sem contact_id — ignorado")
        return {"status": "ignored", "reason": "no_contact_id"}

    logger.info(f"[ghl_webhook] Recebido — contact_id: {ghl_contact_id}")

    email_n    = normalize_email(body.get("email"))
    telefone_n = normalize_phone(body.get("phone"))

    utm_fields = _extract_utm_fields(body)

    lead_data = {
        "funnel_id":       funnel_id,
        "ghl_contact_id":  ghl_contact_id,
        "email_norm":      email_n,
        "telefone_norm":   telefone_n,
        "nome":            body.get("full_name") or body.get("name"),
        "raw_ghl":         body,
        "updated_at":      datetime.utcnow().isoformat(),
        **{k: v for k, v in utm_fields.items() if v is not None},
    }

    # UPSERT por ghl_contact_id
    existing_res = (
        db.table("leads")
        .select("id, origem_registro")
        .eq("ghl_contact_id", ghl_contact_id)
        .limit(1)
        .execute()
    )

    if existing_res.data:
        lead_id = existing_res.data[0]["id"]
        # Só atualiza campos de atribuição (não sobrescreve dados da planilha)
        update = {k: v for k, v in lead_data.items()
                  if k in ("email_norm", "telefone_norm", "nome", "raw_ghl", "updated_at",
                           "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
                           "fbclid", "fb_ad_id", "fb_campaign_id", "fb_adset_id",
                           "attribution_first", "attribution_last")
                  and v is not None}
        if existing_res.data[0]["origem_registro"] == "planilha":
            update["origem_registro"] = "ambos"
        db.table("leads").update(update).eq("id", lead_id).execute()
    else:
        lead_data["origem_registro"] = "ghl"
        res = db.table("leads").insert(lead_data).execute()
        lead_id = res.data[0]["id"] if res.data else None

    # Roda o motor de cruzamento para este lead
    if lead_id:
        try:
            run_match(funnel_id)
        except Exception as exc:
            logger.warning(f"[ghl_webhook] match falhou (não-crítico): {exc}")

    return {"status": "ok", "lead_id": lead_id, "contact_id": ghl_contact_id}
