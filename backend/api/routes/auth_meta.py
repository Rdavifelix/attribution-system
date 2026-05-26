"""
OAuth flow para Meta Ads.

GET  /auth/meta              → redireciona para Facebook OAuth
GET  /auth/meta/callback     → troca code por token, redireciona para /settings
GET  /auth/meta/accounts     → lista ad accounts disponíveis (usa token salvo)
POST /auth/meta/account      → salva ad_account_id selecionado no funil
DELETE /auth/meta            → desconecta (remove token do banco)
GET  /auth/meta/status       → retorna se está conectado e qual conta
"""
from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from backend.config.settings import settings
from backend.db.client import db

router = APIRouter(prefix="/auth/meta", tags=["meta-oauth"])

FB_OAUTH_URL = "https://www.facebook.com"
FB_GRAPH_URL = "https://graph.facebook.com"
SCOPES = "ads_read,ads_management,business_management,read_insights"


def _get_stored_token() -> Optional[str]:
    try:
        res = db.table("system_settings").select("value").eq("key", "meta_access_token").execute()
        if res.data:
            return res.data[0]["value"]
    except Exception:
        pass  # tabela ainda não criada
    return None


def _save_token(token: str) -> None:
    db.table("system_settings").upsert(
        {"key": "meta_access_token", "value": token},
        on_conflict="key",
    ).execute()


@router.get("")
def meta_oauth_start():
    """Inicia o fluxo OAuth — redireciona para o Facebook."""
    url = (
        f"{FB_OAUTH_URL}/{settings.meta_api_version}/dialog/oauth"
        f"?client_id={settings.meta_app_id}"
        f"&redirect_uri={settings.meta_oauth_redirect_uri}"
        f"&scope={SCOPES}"
        f"&response_type=code"
    )
    return RedirectResponse(url)


@router.get("/callback")
def meta_oauth_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
):
    """
    Facebook redireciona aqui com ?code=xxx
    Troca o code por um short-lived token, depois converte para long-lived (60 dias).
    """
    if error or not code:
        return RedirectResponse(f"{settings.frontend_url}/settings?meta_error=access_denied")

    # 1. Troca code por short-lived token
    resp = httpx.get(
        f"{FB_GRAPH_URL}/{settings.meta_api_version}/oauth/access_token",
        params={
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "redirect_uri": settings.meta_oauth_redirect_uri,
            "code": code,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        return RedirectResponse(f"{settings.frontend_url}/settings?meta_error=token_exchange")

    short_token = resp.json().get("access_token")

    # 2. Converte para long-lived token (válido por 60 dias)
    resp2 = httpx.get(
        f"{FB_GRAPH_URL}/{settings.meta_api_version}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "fb_exchange_token": short_token,
        },
        timeout=15,
    )
    long_token = resp2.json().get("access_token", short_token)

    # 3. Salva no banco
    _save_token(long_token)

    return RedirectResponse(f"{settings.frontend_url}/settings?meta_connected=1")


@router.get("/status")
def meta_status():
    """Retorna se o Meta está conectado e qual conta está selecionada."""
    token = _get_stored_token()
    if not token:
        return {"connected": False}

    # Verifica se o token ainda é válido
    resp = httpx.get(
        f"{FB_GRAPH_URL}/me",
        params={"access_token": token, "fields": "id,name"},
        timeout=10,
    )
    if resp.status_code != 200:
        return {"connected": False, "error": "token_invalid"}

    user = resp.json()

    # Busca conta selecionada no funil 1
    funnel = db.table("funnels").select("meta_ad_account_id").eq("id", 1).execute()
    account_id = funnel.data[0]["meta_ad_account_id"] if funnel.data else None

    return {
        "connected": True,
        "user_name": user.get("name"),
        "selected_account": account_id,
    }


@router.get("/accounts")
def list_meta_accounts():
    """Lista todas as contas de anúncio disponíveis para o token salvo."""
    token = _get_stored_token()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Meta não conectado. Acesse /auth/meta primeiro.",
        )

    resp = httpx.get(
        f"{FB_GRAPH_URL}/{settings.meta_api_version}/me/adaccounts",
        params={
            "access_token": token,
            "fields": "id,name,account_status,currency,business",
            "limit": 50,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.json())

    accounts = resp.json().get("data", [])

    # Marca qual está selecionada
    funnel = db.table("funnels").select("meta_ad_account_id").eq("id", 1).execute()
    selected = funnel.data[0]["meta_ad_account_id"] if funnel.data else None

    STATUS_LABELS = {
        1: "Ativa",
        2: "Desativada",
        3: "Não confirmada",
        7: "Pendente",
        9: "Em revisão",
    }

    return {
        "accounts": [
            {
                "id": a["id"],
                "name": a.get("name", ""),
                "status": STATUS_LABELS.get(a.get("account_status"), "Desconhecido"),
                "currency": a.get("currency", ""),
                "business": a.get("business", {}).get("name", ""),
                "selected": a["id"] == selected,
            }
            for a in accounts
        ]
    }


@router.post("/account")
def select_meta_account(payload: dict):
    """
    Salva a conta de anúncio selecionada no funil.
    Body: {"account_id": "act_123456", "funnel_id": 1}
    """
    account_id = payload.get("account_id")
    funnel_id = payload.get("funnel_id", 1)

    if not account_id:
        raise HTTPException(status_code=400, detail="account_id obrigatório")

    db.table("funnels").update(
        {"meta_ad_account_id": account_id}
    ).eq("id", funnel_id).execute()

    # Também salva no system_settings (para o meta_sync usar)
    db.table("system_settings").upsert(
        {"key": f"meta_ad_account_id_funnel_{funnel_id}", "value": account_id},
        on_conflict="key",
    ).execute()

    return {"ok": True, "account_id": account_id, "funnel_id": funnel_id}


@router.delete("")
def disconnect_meta():
    """Remove o token do banco (desconecta Meta)."""
    db.table("system_settings").delete().eq("key", "meta_access_token").execute()
    return {"ok": True, "message": "Meta desconectado"}
