"""
Ingestão da planilha de Leads → banco (Supabase).

Fluxo por linha:
  1. Normaliza email/telefone (chaves de cruzamento)
  2. UPSERT em `leads` (enriquece registro GHL ou cria novo)
  3. Desempilha Call 1 (colunas 12-27) → aplica de-para → aplica deriver → UPSERT em `calls`
  4. Se bloco Call 2 (cols 28-34) tiver data → idem para Call 2
  5. Consolida flags do lead (tem_call_realizada, virou_venda, etc.)
  6. Armazena linha bruta em raw_planilha

Idempotente: reimportar a mesma planilha atualiza, não duplica.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from backend.config.settings import settings
from backend.config.depara import normalize_value
from backend.db.client import db
from backend.engine.normalizer import (
    normalize_email,
    normalize_phone,
    normalize_money,
    normalize_date,
)
from backend.engine.deriver import derive_call_flags, consolidate_lead_flags

logger = logging.getLogger(__name__)

# ─── Mapeamento de colunas (0-based) ────────────────────────────────────────
# Bloco LEAD
COL_ORIGEM          = 0
COL_INSTAGRAM       = 1
COL_EMAIL           = 2
COL_NOME            = 3
COL_TELEFONE        = 4
COL_FATURAMENTO     = 5
COL_PROFISSAO       = 6
COL_MQL             = 7
COL_SOCIO           = 8
COL_LEAD_SCORING    = 9
COL_DATA_CADASTRO   = 10
COL_DATA_CONTATO    = 11

# Bloco CALL 1
COL1_DATA_AGEND     = 12
COL1_DATA_CALL      = 13
COL1_HORA_CALL      = 14
COL1_SDR            = 15
COL1_STATUS_CALL    = 16
COL1_STATUS_VENDA   = 17
COL1_MOTIVO_NOSHOW  = 18
COL1_CASH           = 19
COL1_VALOR_TOTAL    = 20
COL1_CLOSER         = 21
COL1_VALOR          = 22
COL1_DATA_VENDA     = 23
COL1_PRODUTO        = 24   # CONCLUSÃO → produto (MFA/PAA)
COL1_RAZAO_PERDA    = 25
COL1_LINK_REUNIAO   = 26
COL1_OBSERVACOES    = 27

# Bloco CALL 2 (mais curto; closer herda da Call 1)
COL2_DATA_AGEND     = 28
COL2_HORA_CALL      = 29
COL2_STATUS_CALL    = 30
COL2_STATUS_VENDA   = 31
COL2_MOTIVO_NOSHOW  = 32
COL2_CASH           = 33
COL2_VALOR_TOTAL    = 34


def _cell(row: list, col: int) -> str:
    """Retorna a célula ou string vazia se a coluna não existir."""
    try:
        return str(row[col]).strip()
    except IndexError:
        return ""


def _get_sheet_rows(sheet_id: str, tab_name: str) -> list[list]:
    """Abre a planilha e retorna todas as linhas (exceto cabeçalho)."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    sa_info = json.loads(settings.google_service_account_json)
    creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id)
    ws = sheet.worksheet(tab_name)
    # Retorna tudo como strings (values_render_option=FORMATTED_VALUE é o padrão)
    rows = ws.get_all_values()
    return rows[1:] if rows else []  # pula cabeçalho


def _build_call_dict(
    row: list,
    numero_call: int,
    lead_id: str,
    funnel_id: int,
    closer_call1: str,
) -> dict | None:
    """
    Extrai os campos de uma call (1 ou 2) de uma linha da planilha.
    Retorna None se o bloco não tiver data de agendamento nem data de call.
    """
    if numero_call == 1:
        data_agend    = _cell(row, COL1_DATA_AGEND)
        data_call     = _cell(row, COL1_DATA_CALL)
        hora_call     = _cell(row, COL1_HORA_CALL)
        sdr           = _cell(row, COL1_SDR)
        status_call_r = _cell(row, COL1_STATUS_CALL)
        status_venda_r= _cell(row, COL1_STATUS_VENDA)
        motivo_noshow = _cell(row, COL1_MOTIVO_NOSHOW)
        cash_r        = _cell(row, COL1_CASH)
        valor_total_r = _cell(row, COL1_VALOR_TOTAL)
        closer        = _cell(row, COL1_CLOSER)
        valor_r       = _cell(row, COL1_VALOR)
        data_venda    = _cell(row, COL1_DATA_VENDA)
        produto       = _cell(row, COL1_PRODUTO)
        razao_perda   = _cell(row, COL1_RAZAO_PERDA)
        link_reuniao  = _cell(row, COL1_LINK_REUNIAO)
        observacoes   = _cell(row, COL1_OBSERVACOES)
    else:
        data_agend    = _cell(row, COL2_DATA_AGEND)
        data_call     = ""   # bloco 2 não tem data_call separada; usa data_agend como referência
        hora_call     = _cell(row, COL2_HORA_CALL)
        sdr           = ""   # bloco 2 não repete SDR
        status_call_r = _cell(row, COL2_STATUS_CALL)
        status_venda_r= _cell(row, COL2_STATUS_VENDA)
        motivo_noshow = _cell(row, COL2_MOTIVO_NOSHOW)
        cash_r        = _cell(row, COL2_CASH)
        valor_total_r = _cell(row, COL2_VALOR_TOTAL)
        closer        = closer_call1   # herda da Call 1
        valor_r       = ""
        data_venda    = ""
        produto       = ""
        razao_perda   = ""
        link_reuniao  = ""
        observacoes   = ""

    # Bloco vazio → descarta
    if not data_agend and not data_call and not status_call_r and not status_venda_r:
        return None

    # Normaliza datas
    data_agend_n = normalize_date(data_agend)
    data_call_n  = normalize_date(data_call) if data_call else None
    data_venda_n = normalize_date(data_venda) if data_venda else None

    # Canonicaliza status
    sc_norm = normalize_value("status_call",  status_call_r)
    sv_norm = normalize_value("status_venda", status_venda_r)

    call = {
        "lead_id":          lead_id,
        "funnel_id":        funnel_id,
        "numero_call":      numero_call,
        "data_agendamento": data_agend_n,
        "data_call":        data_call_n,
        "hora_call":        hora_call or None,
        "data_venda":       data_venda_n,
        "sdr":              sdr or None,
        "closer":           closer or None,
        "status_call_raw":  status_call_r or None,
        "status_call_norm": sc_norm,
        "status_venda_raw": status_venda_r or None,
        "status_venda_norm":sv_norm,
        "motivo_noshow":    motivo_noshow or None,
        "razao_perda":      razao_perda or None,
        "cash_collected":   normalize_money(cash_r),
        "valor_total":      normalize_money(valor_total_r),
        "valor":            normalize_money(valor_r),
        "produto":          produto or None,
        "link_reuniao":     link_reuniao or None,
        "observacoes":      observacoes or None,
    }

    # Deriva flags booleanas
    flags = derive_call_flags(call)
    call.update(flags)

    return call


def _upsert_lead(row: list, funnel_id: int) -> str | None:
    """
    Faz UPSERT do lead no banco.
    Retorna o UUID do lead ou None se não houver identificador.
    """
    email_raw   = _cell(row, COL_EMAIL)
    telefone_raw= _cell(row, COL_TELEFONE)
    email_n     = normalize_email(email_raw)
    telefone_n  = normalize_phone(telefone_raw)

    if not email_n and not telefone_n:
        logger.warning("Linha sem email nem telefone — ignorada")
        return None

    lead_data = {
        "funnel_id":        funnel_id,
        "email_norm":       email_n,
        "telefone_norm":    telefone_n,
        "nome":             _cell(row, COL_NOME) or None,
        "origem_planilha":  _cell(row, COL_ORIGEM) or None,
        "instagram":        _cell(row, COL_INSTAGRAM) or None,
        "faturamento":      _cell(row, COL_FATURAMENTO) or None,
        "profissao":        _cell(row, COL_PROFISSAO) or None,
        "mql":              _cell(row, COL_MQL) or None,
        "tem_socio":        _cell(row, COL_SOCIO) or None,
        "lead_scoring":     _cell(row, COL_LEAD_SCORING) or None,
        "data_cadastro":    normalize_date(_cell(row, COL_DATA_CADASTRO)),
        "data_contato":     normalize_date(_cell(row, COL_DATA_CONTATO)),
        "raw_planilha":     row,  # linha bruta para auditoria
        "updated_at":       datetime.utcnow().isoformat(),
    }

    # Tenta encontrar lead existente por email ou telefone no mesmo funil
    existing_id: str | None = None

    if email_n:
        res = (
            db.table("leads")
            .select("id, origem_registro")
            .eq("funnel_id", funnel_id)
            .eq("email_norm", email_n)
            .limit(1)
            .execute()
        )
        if res.data:
            existing_id = res.data[0]["id"]

    if not existing_id and telefone_n:
        res = (
            db.table("leads")
            .select("id, origem_registro")
            .eq("funnel_id", funnel_id)
            .eq("telefone_norm", telefone_n)
            .limit(1)
            .execute()
        )
        if res.data:
            existing_id = res.data[0]["id"]

    if existing_id:
        # Enriquece o lead existente (não sobrescreve UTMs do GHL)
        update_data = {k: v for k, v in lead_data.items()
                       if k not in ("funnel_id",) and v is not None}
        # Atualiza origem_registro para 'ambos' se era 'ghl'
        orig_res = db.table("leads").select("origem_registro").eq("id", existing_id).execute()
        if orig_res.data and orig_res.data[0]["origem_registro"] == "ghl":
            update_data["origem_registro"] = "ambos"

        db.table("leads").update(update_data).eq("id", existing_id).execute()
        return existing_id
    else:
        # Cria novo lead (vindo só da planilha)
        lead_data["origem_registro"] = "planilha"
        res = db.table("leads").insert(lead_data).execute()
        return res.data[0]["id"] if res.data else None


def _upsert_call(call: dict) -> None:
    """UPSERT de uma call — chave: (lead_id, numero_call)."""
    call["updated_at"] = datetime.utcnow().isoformat()
    db.table("calls").upsert(call, on_conflict="lead_id,numero_call").execute()


def _update_lead_flags(lead_id: str) -> None:
    """
    Recalcula as flags consolidadas do lead a partir de todas as suas calls.
    Garante consistência mesmo em re-ingestões parciais.
    """
    res = db.table("calls").select(
        "data_agendamento, call_realizada, houve_venda, venda_revertida"
    ).eq("lead_id", lead_id).execute()

    calls = res.data or []
    flags = consolidate_lead_flags(calls)
    flags["updated_at"] = datetime.utcnow().isoformat()
    db.table("leads").update(flags).eq("id", lead_id).execute()


def sync_sheet(
    sheet_id: str | None = None,
    tab_name: str | None = None,
    funnel_id: int | None = None,
) -> dict:
    """
    Ponto de entrada principal.
    Retorna um resumo com contadores de linhas processadas.
    """
    sheet_id  = sheet_id  or settings.sheet_id
    tab_name  = tab_name  or settings.sheet_tab
    funnel_id = funnel_id or settings.default_funnel_id

    logger.info(f"[sheets_sync] Iniciando — sheet={sheet_id}, tab={tab_name}, funnel={funnel_id}")

    rows = _get_sheet_rows(sheet_id, tab_name)
    stats = {"linhas": len(rows), "leads": 0, "calls": 0, "erros": 0}

    for i, row in enumerate(rows, start=2):  # linha 2 = primeira linha de dados
        try:
            lead_id = _upsert_lead(row, funnel_id)
            if not lead_id:
                stats["erros"] += 1
                continue

            stats["leads"] += 1
            closer_call1 = _cell(row, COL1_CLOSER)

            # Call 1
            call1 = _build_call_dict(row, 1, lead_id, funnel_id, closer_call1)
            if call1:
                _upsert_call(call1)
                stats["calls"] += 1

            # Call 2 (só se o bloco tiver algum dado)
            call2 = _build_call_dict(row, 2, lead_id, funnel_id, closer_call1)
            if call2:
                _upsert_call(call2)
                stats["calls"] += 1

            # Atualiza flags consolidadas do lead
            _update_lead_flags(lead_id)

        except Exception as exc:
            logger.error(f"[sheets_sync] Erro na linha {i}: {exc}", exc_info=True)
            stats["erros"] += 1

    logger.info(f"[sheets_sync] Concluído — {stats}")
    return stats
