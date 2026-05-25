"""
Rotas do dashboard de atribuição.

Todos os endpoints retornam dados já agregados, prontos para o frontend
renderizar sem precisar calcular nada além de indicadores derivados simples.
"""
from __future__ import annotations
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from backend.db.client import db

router = APIRouter(prefix="/api/dashboard")


def _default_period() -> tuple[str, str]:
    end   = date.today().isoformat()
    start = (date.today() - timedelta(days=30)).isoformat()
    return start, end


# ─── /ranking — Tabela principal por anúncio ────────────────────────────────
@router.get("/ranking")
def ranking(
    funnel_id:    int            = Query(default=1),
    period_start: Optional[str]  = Query(default=None),
    period_end:   Optional[str]  = Query(default=None),
    campaign_id:  Optional[str]  = Query(default=None),
    produto:      Optional[str]  = Query(default=None),
    sdr:          Optional[str]  = Query(default=None),
    closer:       Optional[str]  = Query(default=None),
):
    start, end = period_start or _default_period()[0], period_end or _default_period()[1]

    # Query via view v_ranking_ad (criada no schema.sql)
    q = (
        db.table("v_ranking_ad")
        .select("*")
        .eq("funnel_id", funnel_id)
        .gte("data", start)
        .lte("data", end)
    )
    if campaign_id:
        q = q.eq("campaign_id", campaign_id)
    if produto:
        q = q.eq("produto", produto)
    if sdr:
        q = q.eq("sdr", sdr)
    if closer:
        q = q.eq("closer", closer)

    rows = q.execute().data or []

    # Agrega por anúncio (a view retorna 1 linha por (dia, lead, call))
    ads: dict[str, dict] = {}
    for r in rows:
        ad_id = r["ad_id"]
        if ad_id not in ads:
            ads[ad_id] = {
                "ad_id":        ad_id,
                "ad_name":      r["ad_name"],
                "adset_id":     r["adset_id"],
                "adset_name":   r["adset_name"],
                "campaign_id":  r["campaign_id"],
                "campaign_name":r["campaign_name"],
                "investido":    0.0,
                "impressoes":   0,
                "cliques":      0,
                "_leads":       set(),
                "_mqls":        set(),
                "calls_agendadas":  0,
                "calls_realizadas": 0,
                "noshows":          0,
                "vendas":           0,
                "vendas_revertidas":0,
                "cash_collected":   0.0,
                "valor_total":      0.0,
                "_valor_total_max": 0.0,
            }
        a = ads[ad_id]
        a["investido"]  += r.get("spend") or 0
        a["impressoes"] += r.get("impressions") or 0
        a["cliques"]    += r.get("clicks") or 0

        # Leads e MQLs (deduplicados por lead_id)
        lid = r.get("lead_id")
        if lid:
            a["_leads"].add(lid)
            if r.get("mql"):
                a["_mqls"].add(lid)

        # Calls
        if r.get("call_id"):
            if r.get("data_agendamento"):
                a["calls_agendadas"]  += 1
            if r.get("call_realizada"):
                a["calls_realizadas"] += 1
            if r.get("houve_noshow"):
                a["noshows"]          += 1
            if r.get("houve_venda"):
                a["vendas"]           += 1
                if r.get("venda_revertida"):
                    a["vendas_revertidas"] += 1
                # cash = soma; valor_total = max
                a["cash_collected"] += r.get("cash_collected") or 0
                vt = r.get("valor_total") or 0
                if vt > a["_valor_total_max"]:
                    a["_valor_total_max"] = vt

    # Serializa e calcula indicadores derivados
    result = []
    for a in ads.values():
        n_leads    = len(a["_leads"])
        n_mqls     = len(a["_mqls"])
        investido  = a["investido"]
        calls_r    = a["calls_realizadas"]
        calls_a    = a["calls_agendadas"]
        vendas     = a["vendas"] - a["vendas_revertidas"]
        cash       = a["cash_collected"]
        valor_tot  = a["_valor_total_max"]

        result.append({
            "ad_id":            a["ad_id"],
            "ad_name":          a["ad_name"],
            "adset_name":       a["adset_name"],
            "campaign_name":    a["campaign_name"],
            "investido":        round(investido, 2),
            "impressoes":       a["impressoes"],
            "cliques":          a["cliques"],
            "leads":            n_leads,
            "mqls":             n_mqls,
            "calls_agendadas":  calls_a,
            "calls_realizadas": calls_r,
            "noshows":          a["noshows"],
            "vendas":           vendas,
            "vendas_brutas":    a["vendas"],
            "vendas_revertidas":a["vendas_revertidas"],
            "cash_collected":   round(cash, 2),
            "valor_total":      round(valor_tot, 2),
            # Indicadores derivados
            "cpl":              round(investido / n_leads, 2)      if n_leads   else None,
            "custo_por_call":   round(investido / calls_r, 2)     if calls_r   else None,
            "cac":              round(investido / vendas, 2)       if vendas    else None,
            "roas_cash":        round(cash / investido, 4)         if investido else None,
            "roas_contratado":  round(valor_tot / investido, 4)   if investido else None,
            "taxa_show":        round(calls_r / calls_a, 4)        if calls_a   else None,
            "taxa_fechamento":  round(vendas / calls_r, 4)         if calls_r   else None,
        })

    # Ordena por investido desc
    result.sort(key=lambda x: x["investido"], reverse=True)
    return {"data": result, "periodo": {"start": start, "end": end}}


# ─── /funnel — Funil completo por anúncio ───────────────────────────────────
@router.get("/funnel")
def funnel(
    funnel_id:    int           = Query(default=1),
    period_start: Optional[str] = Query(default=None),
    period_end:   Optional[str] = Query(default=None),
    campaign_id:  Optional[str] = Query(default=None),
):
    start, end = period_start or _default_period()[0], period_end or _default_period()[1]

    q = (
        db.table("v_ranking_ad")
        .select("campaign_name, ad_id, ad_name, lead_id, mql, call_id, "
                "data_agendamento, call_realizada, houve_venda, venda_revertida, "
                "impressions, clicks, spend")
        .eq("funnel_id", funnel_id)
        .gte("data", start)
        .lte("data", end)
    )
    if campaign_id:
        q = q.eq("campaign_id", campaign_id)

    rows = q.execute().data or []

    # Agrega tudo em um único funil
    agg = {
        "impressoes":       0,
        "cliques":          0,
        "leads":            set(),
        "mqls":             set(),
        "calls_agendadas":  set(),
        "calls_realizadas": set(),
        "vendas":           0,
    }
    for r in rows:
        agg["impressoes"] += r.get("impressions") or 0
        agg["cliques"]    += r.get("clicks") or 0
        if r.get("lead_id"):
            agg["leads"].add(r["lead_id"])
            if r.get("mql"):
                agg["mqls"].add(r["lead_id"])
        if r.get("call_id"):
            if r.get("data_agendamento"):
                agg["calls_agendadas"].add(r["call_id"])
            if r.get("call_realizada"):
                agg["calls_realizadas"].add(r["call_id"])
            if r.get("houve_venda") and not r.get("venda_revertida"):
                agg["vendas"] += 1

    steps = [
        {"etapa": "Impressões",         "valor": agg["impressoes"]},
        {"etapa": "Cliques",            "valor": agg["cliques"]},
        {"etapa": "Leads",              "valor": len(agg["leads"])},
        {"etapa": "MQLs",               "valor": len(agg["mqls"])},
        {"etapa": "Calls Agendadas",    "valor": len(agg["calls_agendadas"])},
        {"etapa": "Calls Realizadas",   "valor": len(agg["calls_realizadas"])},
        {"etapa": "Vendas",             "valor": agg["vendas"]},
    ]
    # Adiciona taxa de conversão entre etapas
    for i in range(1, len(steps)):
        prev = steps[i - 1]["valor"]
        curr = steps[i]["valor"]
        steps[i]["taxa"] = round(curr / prev, 4) if prev else None

    return {"steps": steps, "periodo": {"start": start, "end": end}}


# ─── /team — Performance por SDR e Closer ───────────────────────────────────
@router.get("/team")
def team(
    funnel_id:    int           = Query(default=1),
    period_start: Optional[str] = Query(default=None),
    period_end:   Optional[str] = Query(default=None),
):
    start, end = period_start or _default_period()[0], period_end or _default_period()[1]

    rows = (
        db.table("calls")
        .select("sdr, closer, call_realizada, houve_venda, venda_revertida, "
                "houve_noshow, cash_collected, data_agendamento, data_call")
        .eq("funnel_id", funnel_id)
        .gte("data_agendamento", start)
        .lte("data_agendamento", end)
        .execute()
        .data or []
    )

    sdrs:    dict[str, dict] = {}
    closers: dict[str, dict] = {}

    def _agg(store, key):
        if not key:
            return
        if key not in store:
            store[key] = {
                "nome": key, "calls_agendadas": 0, "calls_realizadas": 0,
                "noshows": 0, "vendas": 0, "cash_collected": 0.0
            }
        return store[key]

    for r in rows:
        s = _agg(sdrs,    r.get("sdr"))
        c = _agg(closers, r.get("closer"))
        for ag in [s, c]:
            if ag is None:
                continue
            if r.get("data_agendamento"):
                ag["calls_agendadas"] += 1
            if r.get("call_realizada"):
                ag["calls_realizadas"] += 1
            if r.get("houve_noshow"):
                ag["noshows"] += 1
            if r.get("houve_venda") and not r.get("venda_revertida"):
                ag["vendas"] += 1
                ag["cash_collected"] += r.get("cash_collected") or 0

    def _add_rates(lst):
        for ag in lst:
            ca = ag["calls_agendadas"]
            cr = ag["calls_realizadas"]
            v  = ag["vendas"]
            ag["taxa_show"]       = round(cr / ca, 4) if ca else None
            ag["taxa_fechamento"] = round(v  / cr, 4) if cr else None
        return lst

    return {
        "sdrs":    _add_rates(list(sdrs.values())),
        "closers": _add_rates(list(closers.values())),
        "periodo": {"start": start, "end": end},
    }


# ─── /quality — Painel de qualidade de dados ────────────────────────────────
@router.get("/quality")
def quality(funnel_id: int = Query(default=1)):
    # Total de leads
    total_res = (
        db.table("leads")
        .select("id", count="exact")
        .eq("funnel_id", funnel_id)
        .execute()
    )
    total = total_res.count or 0

    # Leads com match
    matched_res = (
        db.table("lead_ad_match")
        .select("lead_id", count="exact")
        .execute()
    )
    matched = matched_res.count or 0

    # Leads só da planilha (sem GHL)
    planilha_only = (
        db.table("leads")
        .select("id", count="exact")
        .eq("funnel_id", funnel_id)
        .eq("origem_registro", "planilha")
        .execute()
        .count or 0
    )

    # Calls com status desconhecido
    unknown_status = (
        db.table("calls")
        .select("id", count="exact")
        .eq("funnel_id", funnel_id)
        .like("status_call_norm", "DESCONHECIDO%")
        .execute()
        .count or 0
    )

    # Calls sem data de call e sem data de agendamento
    no_date = (
        db.table("calls")
        .select("id", count="exact")
        .eq("funnel_id", funnel_id)
        .is_("data_call", "null")
        .is_("data_agendamento", "null")
        .execute()
        .count or 0
    )

    coverage = round(matched / total, 4) if total else 0

    return {
        "total_leads":             total,
        "leads_com_match":         matched,
        "cobertura_atribuicao":    coverage,
        "leads_so_planilha":       planilha_only,
        "calls_status_desconhecido": unknown_status,
        "calls_sem_data":          no_date,
        "alertas": [
            {"tipo": "cobertura_baixa", "ativo": coverage < 0.7,
             "mensagem": f"Apenas {coverage:.0%} dos leads têm atribuição de anúncio"},
            {"tipo": "status_desconhecido", "ativo": unknown_status > 0,
             "mensagem": f"{unknown_status} calls com STATUS CALL não mapeado — atualizar depara_status"},
        ],
    }


# ─── /funnels — Lista de funis ───────────────────────────────────────────────
@router.get("/funnels")
def list_funnels():
    res = db.table("funnels").select("id, nome, ativo, utm_funnel_code").eq("ativo", True).execute()
    return {"funnels": res.data or []}
