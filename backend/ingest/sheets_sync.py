"""
Ingestão da planilha de Leads → banco (Supabase).

Fluxo por linha:
  1. Normaliza email/telefone (chaves de cruzamento)
  2. UPSERT em `leads` (enriquece registro GHL ou cria novo)
  3. Desempilha Call 1 (colunas 12-27) → aplica de-para → aplica deriver → UPSERT em `calls`
  4. Se bloco Call 2 (cols 30-36) tiver data → idem para Call 2
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
COL1_PRODUTO        = 22   # 'Produto vendido' → MFA / PAA / MR
COL1_VALOR          = 23   # 'VALOR DA OPORTUNIDADE'
COL1_DATA_VENDA     = 24   # 'DATA CONCLUSÃO'
COL1_RAZAO_PERDA    = 25
COL1_LINK_REUNIAO   = 26
COL1_OBSERVACOES    = 27

# Colunas 28 e 29 são vazias na planilha (separador visual)

# Bloco CALL 2 (mais curto; closer herda da Call 1)
# Começa no índice 30 conforme cabeçalho real da planilha
COL2_DATA_AGEND     = 30   # 'DATA 2 CALL'
COL2_HORA_CALL      = 31   # 'HORA 2 CALL'
COL2_STATUS_CALL    = 32   # 'STATUS CALL'
COL2_STATUS_VENDA   = 33   # 'STATUS VENDA'
COL2_MOTIVO_NOSHOW  = 34   # 'MOTIVO NOSHOW'
COL2_CASH           = 35   # 'CASH COLLECTED'
COL2_VALOR_TOTAL    = 36   # 'VALOR TOTAL'

# Coluna extra — fórmula na planilha, pode ter #N/A
COL_AD_NAME_EMAIL   = 37   # 'AD NAME Email'


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
    # A planilha tem 3 linhas iniciais a pular:
    #   Linha 1 = cabeçalho principal
    #   Linha 2 = linha de totais/resumo (ex: contagem de VENDAS, SINAL…)
    #   Linha 3 = sub-cabeçalho duplicado
    # Os dados reais começam na linha 4 (índice 3)
    return rows[3:] if rows else []


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


def _load_existing_leads(funnel_id: int) -> tuple[dict, dict]:
    """
    Carrega email_norm → id e telefone_norm → id de todos os leads do funil.
    Usado no modo batch para eliminar SELECT por linha.
    """
    email_map: dict[str, str] = {}
    phone_map: dict[str, str] = {}
    page = 0
    page_size = 1000
    while True:
        res = (
            db.table("leads")
            .select("id, email_norm, telefone_norm")
            .eq("funnel_id", funnel_id)
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        if not res.data:
            break
        for r in res.data:
            if r.get("email_norm"):
                email_map[r["email_norm"]] = r["id"]
            if r.get("telefone_norm"):
                phone_map[r["telefone_norm"]] = r["id"]
        if len(res.data) < page_size:
            break
        page += 1
    return email_map, phone_map


def sync_sheet(
    sheet_id: str | None = None,
    tab_name: str | None = None,
    funnel_id: int | None = None,
) -> dict:
    """
    Ponto de entrada principal.
    Retorna um resumo com contadores de linhas processadas.

    Modo batch: pré-carrega leads existentes em memória para eliminar
    SELECT duplicados e acelerar sync em 5-10x vs modo linha-a-linha.
    """
    sheet_id  = sheet_id  or settings.sheet_id
    tab_name  = tab_name  or settings.sheet_tab
    funnel_id = funnel_id or settings.default_funnel_id

    logger.info(f"[sheets_sync] Iniciando — sheet={sheet_id}, tab={tab_name}, funnel={funnel_id}")

    rows = _get_sheet_rows(sheet_id, tab_name)
    stats = {"linhas": len(rows), "leads": 0, "calls": 0, "erros": 0}

    # Pré-carrega leads existentes (evita N SELECTs por linha)
    email_cache, phone_cache = _load_existing_leads(funnel_id)
    logger.info(f"[sheets_sync] Leads em cache: {len(email_cache)} emails, {len(phone_cache)} telefones")

    # Lista de lead_ids a ter flags recalculadas no final
    processed_lead_ids: list[str] = []

    for i, row in enumerate(rows, start=4):  # linha 4 = primeira linha de dados reais
        try:
            email_n   = normalize_email(_cell(row, COL_EMAIL))
            telefone_n= normalize_phone(_cell(row, COL_TELEFONE))

            if not email_n and not telefone_n:
                stats["erros"] += 1
                continue

            # Lookup em cache primeiro
            existing_id: str | None = (
                email_cache.get(email_n) if email_n else None
            ) or (
                phone_cache.get(telefone_n) if telefone_n else None
            )

            if existing_id:
                # Atualiza em vez de consultar banco
                update_data = {
                    "nome":            _cell(row, COL_NOME) or None,
                    "origem_planilha": _cell(row, COL_ORIGEM) or None,
                    "instagram":       _cell(row, COL_INSTAGRAM) or None,
                    "faturamento":     _cell(row, COL_FATURAMENTO) or None,
                    "profissao":       _cell(row, COL_PROFISSAO) or None,
                    "mql":             _cell(row, COL_MQL) or None,
                    "tem_socio":       _cell(row, COL_SOCIO) or None,
                    "lead_scoring":    _cell(row, COL_LEAD_SCORING) or None,
                    "data_cadastro":   normalize_date(_cell(row, COL_DATA_CADASTRO)),
                    "data_contato":    normalize_date(_cell(row, COL_DATA_CONTATO)),
                    "raw_planilha":    row,
                    "updated_at":      datetime.utcnow().isoformat(),
                }
                update_data = {k: v for k, v in update_data.items() if v is not None}
                db.table("leads").update(update_data).eq("id", existing_id).execute()
                lead_id = existing_id
            else:
                # INSERT novo lead
                lead_data = {
                    "funnel_id":       funnel_id,
                    "email_norm":      email_n,
                    "telefone_norm":   telefone_n,
                    "nome":            _cell(row, COL_NOME) or None,
                    "origem_planilha": _cell(row, COL_ORIGEM) or None,
                    "instagram":       _cell(row, COL_INSTAGRAM) or None,
                    "faturamento":     _cell(row, COL_FATURAMENTO) or None,
                    "profissao":       _cell(row, COL_PROFISSAO) or None,
                    "mql":             _cell(row, COL_MQL) or None,
                    "tem_socio":       _cell(row, COL_SOCIO) or None,
                    "lead_scoring":    _cell(row, COL_LEAD_SCORING) or None,
                    "data_cadastro":   normalize_date(_cell(row, COL_DATA_CADASTRO)),
                    "data_contato":    normalize_date(_cell(row, COL_DATA_CONTATO)),
                    "raw_planilha":    row,
                    "origem_registro": "planilha",
                    "updated_at":      datetime.utcnow().isoformat(),
                }
                res = db.table("leads").insert(lead_data).execute()
                if not res.data:
                    stats["erros"] += 1
                    continue
                lead_id = res.data[0]["id"]
                # Atualiza cache local para evitar duplicata se mesma pessoa aparecer duas vezes
                if email_n:
                    email_cache[email_n] = lead_id
                if telefone_n:
                    phone_cache[telefone_n] = lead_id

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

            processed_lead_ids.append(lead_id)

        except Exception as exc:
            logger.error(f"[sheets_sync] Erro na linha {i}: {exc}", exc_info=True)
            stats["erros"] += 1

    # Recalcula flags de todos os leads processados em uma passagem final
    logger.info(f"[sheets_sync] Recalculando flags de {len(processed_lead_ids)} leads...")
    for lead_id in processed_lead_ids:
        try:
            _update_lead_flags(lead_id)
        except Exception as exc:
            logger.warning(f"[sheets_sync] Erro ao atualizar flags do lead {lead_id}: {exc}")

    logger.info(f"[sheets_sync] Concluído — {stats}")
    return stats
