"""
Motor de derivação de flags booleanas para cada call.

Regras confirmadas pelo usuário (Blueprint v2 — Seção 6 + Seção 11):

call_realizada:
  - STATUS CALL = 'VENDA - EM CALL' → TRUE  (call + venda)
  - STATUS CALL ∈ {NAO_REALIZADA, REAGENDADA, CANCELADA} → FALSE
  - STATUS CALL vazio + STATUS VENDA = PERDIDA/FOLLOW_UP/etc. → TRUE
    (usuário confirmou: STATUS CALL fica vazio quando call acontece sem venda)
  - STATUS CALL vazio + data_call preenchida → TRUE
  - Caso contrário → FALSE

houve_venda:
  STATUS VENDA ∈ {VENDA_EM_CALL, VENDA_SINAL, SINAL_RECEBIDO}

venda_revertida:
  STATUS VENDA = REEMBOLSADA

houve_noshow:
  STATUS CALL ∈ {NAO_REALIZADA, CANCELADA}
  OU motivo_noshow contém 'NÃO COMPARECEU' | 'SEM CONFIRMAÇÃO'
"""
from __future__ import annotations

# Valores normalizados que indicam venda fechada
# REEMBOLSADA: foi venda → depois revertida. houve_venda=True + venda_revertida=True.
VENDA_NORMS: frozenset[str] = frozenset({
    "VENDA_EM_CALL",
    "VENDA_SINAL",
    "SINAL_RECEBIDO",
    "REEMBOLSADA",
})

# Valores de STATUS CALL que significam que a call NÃO aconteceu
NO_SHOW_CALL_NORMS: frozenset[str] = frozenset({
    "NAO_REALIZADA",
    "CANCELADA",
})

# STATUS CALL que não bloqueiam call (mas não confirmam sozinhos)
PENDENTE_CALL_NORMS: frozenset[str] = frozenset({
    "REAGENDADA",
})

# STATUS VENDA que provam que a call ACONTECEU
# (mesmo com STATUS CALL vazio — confirmado pelo usuário)
VENDA_IMPLICA_CALL: frozenset[str] = frozenset({
    "PERDIDA",
    "FOLLOW_UP",
    "SEGUNDA_REUNIAO",
    "REAGENDADA",
    "REEMBOLSADA",
    "VENDA_EM_CALL",
    "VENDA_SINAL",
    "SINAL_RECEBIDO",
})

MOTIVO_NOSHOW_KEYWORDS = {"NÃO COMPARECEU", "NAO COMPARECEU", "SEM CONFIRMAÇÃO", "SEM CONFIRMACAO"}


def compute_call_realizada(
    status_call_norm: str,
    status_venda_norm: str,
    data_call: str | None,
    motivo_noshow: str | None,
) -> bool:
    """
    Decide se a call realmente aconteceu.

    Prioridade das regras (da mais específica para a mais genérica):
    1. STATUS CALL = REALIZADA_COM_VENDA → TRUE  (call + venda no mesmo status)
    2. STATUS CALL = REALIZADA → TRUE             (call aconteceu, sem venda)
    3. STATUS CALL ∈ NO_SHOW_CALL_NORMS → FALSE
    4. STATUS CALL = REAGENDADA → FALSE (foi para outra data)
    5. STATUS CALL vazio E STATUS VENDA ∈ VENDA_IMPLICA_CALL → TRUE
    6. STATUS CALL vazio E data_call preenchida → TRUE (inferido)
    7. Caso contrário → FALSE
    """
    sc = status_call_norm or "VAZIO"
    sv = status_venda_norm or "VAZIO"

    if sc == "REALIZADA_COM_VENDA":
        return True
    if sc == "REALIZADA":
        return True
    if sc in NO_SHOW_CALL_NORMS:
        return False
    if sc in PENDENTE_CALL_NORMS:
        return False
    # STATUS CALL vazio ou desconhecido: olhar STATUS VENDA e data
    if sv in VENDA_IMPLICA_CALL:
        return True
    if data_call:
        return True
    return False


def compute_houve_noshow(
    status_call_norm: str,
    motivo_noshow: str | None,
) -> bool:
    sc = status_call_norm or "VAZIO"
    if sc in NO_SHOW_CALL_NORMS:
        return True
    mn = (motivo_noshow or "").strip().upper()
    return any(kw in mn for kw in MOTIVO_NOSHOW_KEYWORDS)


def derive_call_flags(call: dict) -> dict:
    """
    Recebe um dict de call com campos *_norm já preenchidos.
    Retorna um dict com as 4 flags booleanas derivadas.

    Uso:
        flags = derive_call_flags(call_dict)
        call_dict.update(flags)
    """
    sc  = call.get("status_call_norm") or "VAZIO"
    sv  = call.get("status_venda_norm") or "VAZIO"
    dc  = call.get("data_call")
    mn  = call.get("motivo_noshow")

    return {
        "call_realizada":  compute_call_realizada(sc, sv, dc, mn),
        "houve_venda":     sv in VENDA_NORMS,
        "venda_revertida": sv == "REEMBOLSADA",
        "houve_noshow":    compute_houve_noshow(sc, mn),
    }


def consolidate_lead_flags(calls: list[dict]) -> dict:
    """
    A partir de todas as calls de um lead, deriva as flags do lead.

    Regras:
    - tem_call_agendada  = qualquer call com data_agendamento preenchida
    - tem_call_realizada = qualquer call com call_realizada = True
    - virou_venda        = qualquer call com houve_venda = True
                           (descontando venda_revertida APENAS se TODAS as vendas foram revertidas)
    """
    tem_agendada  = any(c.get("data_agendamento") for c in calls)
    tem_realizada = any(c.get("call_realizada") for c in calls)

    # virou_venda: teve pelo menos uma venda não revertida
    vendas = [c for c in calls if c.get("houve_venda")]
    virou  = any(not c.get("venda_revertida") for c in vendas)

    return {
        "tem_call_agendada":  tem_agendada,
        "tem_call_realizada": tem_realizada,
        "virou_venda":        virou,
    }


def aggregate_financials(calls: list[dict]) -> dict:
    """
    Agrega financeiro das calls no nível do lead.

    Regra confirmada (Blueprint v2 — Seção 6.4):
    - cash_collected total = SOMA de todas as calls (cada call traz parcela diferente)
    - valor_total          = MÁXIMO entre as calls (é o mesmo contrato — somar dobraria)
    """
    cash_values = [
        c.get("cash_collected") or 0
        for c in calls
        if c.get("houve_venda") and not c.get("venda_revertida")
    ]
    valor_values = [
        c.get("valor_total") or 0
        for c in calls
        if c.get("houve_venda") and not c.get("venda_revertida")
    ]
    return {
        "cash_collected_total": sum(cash_values),
        "valor_total_contrato": max(valor_values) if valor_values else 0,
    }
