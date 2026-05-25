"""
Tabelas de canonicalização de valores da planilha.

Em produção, estas tabelas são carregadas do banco (tabela depara_status),
o que permite adicionar novos valores sem redeploy.

O módulo expõe a função `normalize_value(campo, raw)` usada pelo sheets_sync.
"""
from __future__ import annotations

# ─── Mapeamentos padrão ──────────────────────────────────────────────────────
# Adicionados aqui como fallback; o banco é a fonte de verdade em produção.

STATUS_CALL_MAP: dict[str, str] = {
    "VENDA - EM CALL":        "REALIZADA_COM_VENDA",
    "CALL NÃO REALIZADA":     "NAO_REALIZADA",
    "CALL REAGENDADA":        "REAGENDADA",
    "CALL CANCELADA":         "CANCELADA",
    "":                       "VAZIO",
}

STATUS_VENDA_MAP: dict[str, str] = {
    "VENDA - EM CALL":        "VENDA_EM_CALL",
    "VENDA - SINAL":          "VENDA_SINAL",
    "SINAL RECEBIDO":         "SINAL_RECEBIDO",
    "REEMBOLSADA":            "REEMBOLSADA",
    "Follow UP":              "FOLLOW_UP",
    "follow up":              "FOLLOW_UP",
    "FOLLOW UP":              "FOLLOW_UP",
    "2a reunião agendada":    "SEGUNDA_REUNIAO",
    "2a reunbião agendada":   "SEGUNDA_REUNIAO",   # typo histórico corrigido
    "2ª REUNIÃO":             "SEGUNDA_REUNIAO",
    "2ª reunião":             "SEGUNDA_REUNIAO",
    "REAGENDADA":             "REAGENDADA",
    "PERDIDA":                "PERDIDA",
    "":                       "VAZIO",
}

_CAMPO_MAP = {
    "status_call":  STATUS_CALL_MAP,
    "status_venda": STATUS_VENDA_MAP,
}

# Cache em memória carregado do banco (sobrescreve os defaults acima)
_db_cache: dict[str, dict[str, str]] = {}


def load_from_db(rows: list[dict]) -> None:
    """
    Carrega a tabela depara_status do banco para o cache em memória.
    Chamado no startup do FastAPI.

    rows: lista de dicts com keys 'campo', 'valor_raw', 'valor_norm'
    """
    global _db_cache
    _db_cache = {}
    for row in rows:
        campo = row["campo"]
        if campo not in _db_cache:
            _db_cache[campo] = {}
        _db_cache[campo][row["valor_raw"]] = row["valor_norm"]


def normalize_value(campo: str, raw: str | None) -> str:
    """
    Converte um valor bruto da planilha para o valor canônico.

    Ordem de resolução:
      1. Cache do banco (carregado via load_from_db)
      2. Mapeamento hardcoded acima
      3. Retorna o próprio raw em UPPER_CASE (novo valor ainda não mapeado)
    """
    if raw is None:
        raw = ""
    raw_stripped = raw.strip()

    # 1. Cache do banco
    if campo in _db_cache and raw_stripped in _db_cache[campo]:
        return _db_cache[campo][raw_stripped]
    # Tentativa case-insensitive no cache
    raw_lower = raw_stripped.lower()
    if campo in _db_cache:
        for k, v in _db_cache[campo].items():
            if k.lower() == raw_lower:
                return v

    # 2. Mapeamento hardcoded
    if campo in _CAMPO_MAP:
        m = _CAMPO_MAP[campo]
        if raw_stripped in m:
            return m[raw_stripped]
        for k, v in m.items():
            if k.lower() == raw_lower:
                return v

    # 3. Valor desconhecido — retorna com flag para auditoria
    if raw_stripped == "":
        return "VAZIO"
    return f"DESCONHECIDO_{raw_stripped.upper().replace(' ', '_')}"
