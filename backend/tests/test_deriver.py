import pytest
from backend.engine.deriver import (
    compute_call_realizada,
    compute_houve_noshow,
    derive_call_flags,
    consolidate_lead_flags,
    aggregate_financials,
)


# ─── compute_call_realizada ──────────────────────────────────────────────────

class TestComputeCallRealizada:
    """Os 4 cenários críticos confirmados pelo usuário."""

    def test_venda_em_call(self):
        """STATUS CALL = REALIZADA_COM_VENDA → call aconteceu"""
        assert compute_call_realizada("REALIZADA_COM_VENDA", "VENDA_EM_CALL", None, None) is True

    def test_nao_realizada(self):
        """STATUS CALL = NAO_REALIZADA → call NÃO aconteceu"""
        assert compute_call_realizada("NAO_REALIZADA", "VAZIO", None, None) is False

    def test_cancelada(self):
        """STATUS CALL = CANCELADA → call NÃO aconteceu"""
        assert compute_call_realizada("CANCELADA", "VAZIO", None, None) is False

    def test_reagendada(self):
        """STATUS CALL = REAGENDADA → call NÃO aconteceu (foi para outra data)"""
        assert compute_call_realizada("REAGENDADA", "VAZIO", None, None) is False

    def test_status_call_vazio_venda_perdida(self):
        """STATUS CALL vazio + STATUS VENDA = PERDIDA → call ACONTECEU (confirmado pelo usuário)"""
        assert compute_call_realizada("VAZIO", "PERDIDA", None, None) is True

    def test_status_call_vazio_follow_up(self):
        """STATUS CALL vazio + STATUS VENDA = FOLLOW_UP → call aconteceu"""
        assert compute_call_realizada("VAZIO", "FOLLOW_UP", None, None) is True

    def test_status_call_vazio_segunda_reuniao(self):
        """STATUS CALL vazio + STATUS VENDA = SEGUNDA_REUNIAO → call aconteceu"""
        assert compute_call_realizada("VAZIO", "SEGUNDA_REUNIAO", None, None) is True

    def test_status_call_vazio_com_data_call(self):
        """STATUS CALL vazio mas tem data_call → inferimos que aconteceu"""
        assert compute_call_realizada("VAZIO", "VAZIO", "2024-03-15", None) is True

    def test_status_call_vazio_sem_dados(self):
        """STATUS CALL vazio + STATUS VENDA vazio + sem data → NÃO aconteceu"""
        assert compute_call_realizada("VAZIO", "VAZIO", None, None) is False

    def test_reembolsada_implica_call(self):
        """Venda reembolsada ainda implica que call aconteceu"""
        assert compute_call_realizada("VAZIO", "REEMBOLSADA", None, None) is True

    def test_realizada_sem_venda(self):
        """STATUS CALL = REALIZADA (617 ocorrências na planilha real) → call aconteceu"""
        assert compute_call_realizada("REALIZADA", "VAZIO", None, None) is True

    def test_realizada_com_followup(self):
        """STATUS CALL = REALIZADA + STATUS VENDA = FOLLOW_UP → call aconteceu"""
        assert compute_call_realizada("REALIZADA", "FOLLOW_UP", None, None) is True


# ─── compute_houve_noshow ────────────────────────────────────────────────────

class TestComputeHouvNoshow:
    def test_nao_realizada(self):
        assert compute_houve_noshow("NAO_REALIZADA", None) is True

    def test_cancelada(self):
        assert compute_houve_noshow("CANCELADA", "") is True

    def test_realizada(self):
        assert compute_houve_noshow("REALIZADA_COM_VENDA", None) is False

    def test_motivo_nao_compareceu(self):
        assert compute_houve_noshow("VAZIO", "Não Compareceu") is True

    def test_motivo_sem_confirmacao(self):
        assert compute_houve_noshow("VAZIO", "SEM CONFIRMAÇÃO") is True

    def test_sem_motivo(self):
        assert compute_houve_noshow("VAZIO", "") is False


# ─── derive_call_flags ───────────────────────────────────────────────────────

class TestDeriveCallFlags:
    def test_venda_em_call(self):
        call = {
            "status_call_norm":  "REALIZADA_COM_VENDA",
            "status_venda_norm": "VENDA_EM_CALL",
            "data_call":         "2024-03-15",
            "motivo_noshow":     None,
        }
        flags = derive_call_flags(call)
        assert flags["call_realizada"]  is True
        assert flags["houve_venda"]     is True
        assert flags["venda_revertida"] is False
        assert flags["houve_noshow"]    is False

    def test_perdida_sem_status_call(self):
        """Cenário clássico: call aconteceu mas não fechou."""
        call = {
            "status_call_norm":  "VAZIO",
            "status_venda_norm": "PERDIDA",
            "data_call":         "2024-03-15",
            "motivo_noshow":     None,
        }
        flags = derive_call_flags(call)
        assert flags["call_realizada"]  is True
        assert flags["houve_venda"]     is False
        assert flags["venda_revertida"] is False
        assert flags["houve_noshow"]    is False

    def test_reembolso(self):
        call = {
            "status_call_norm":  "REALIZADA_COM_VENDA",
            "status_venda_norm": "REEMBOLSADA",
            "data_call":         "2024-03-10",
            "motivo_noshow":     None,
        }
        flags = derive_call_flags(call)
        assert flags["houve_venda"]     is True
        assert flags["venda_revertida"] is True

    def test_noshow(self):
        call = {
            "status_call_norm":  "NAO_REALIZADA",
            "status_venda_norm": "VAZIO",
            "data_call":         None,
            "motivo_noshow":     "Não compareceu",
        }
        flags = derive_call_flags(call)
        assert flags["call_realizada"] is False
        assert flags["houve_noshow"]   is True


# ─── consolidate_lead_flags ──────────────────────────────────────────────────

class TestConsolidateLeadFlags:
    def test_lead_com_venda(self):
        calls = [
            {"data_agendamento": "2024-03-10", "call_realizada": True,
             "houve_venda": True, "venda_revertida": False},
        ]
        flags = consolidate_lead_flags(calls)
        assert flags["tem_call_agendada"]  is True
        assert flags["tem_call_realizada"] is True
        assert flags["virou_venda"]        is True

    def test_lead_venda_revertida(self):
        calls = [
            {"data_agendamento": "2024-03-10", "call_realizada": True,
             "houve_venda": True, "venda_revertida": True},
        ]
        flags = consolidate_lead_flags(calls)
        assert flags["virou_venda"] is False  # revertida → não conta

    def test_duas_calls_segunda_fecha(self):
        calls = [
            {"data_agendamento": "2024-03-10", "call_realizada": True,
             "houve_venda": False, "venda_revertida": False},
            {"data_agendamento": "2024-03-17", "call_realizada": True,
             "houve_venda": True, "venda_revertida": False},
        ]
        flags = consolidate_lead_flags(calls)
        assert flags["tem_call_realizada"] is True
        assert flags["virou_venda"]        is True


# ─── aggregate_financials ────────────────────────────────────────────────────

class TestAggregateFinancials:
    def test_cash_soma_valor_maximo(self):
        """Regra central: cash = soma, valor_total = max."""
        calls = [
            {"houve_venda": True, "venda_revertida": False,
             "cash_collected": 3000, "valor_total": 10000},
            {"houve_venda": True, "venda_revertida": False,
             "cash_collected": 7000, "valor_total": 10000},
        ]
        fin = aggregate_financials(calls)
        assert fin["cash_collected_total"] == 10000
        assert fin["valor_total_contrato"] == 10000

    def test_exclui_call_sem_venda(self):
        calls = [
            {"houve_venda": False, "venda_revertida": False,
             "cash_collected": 5000, "valor_total": 10000},
        ]
        fin = aggregate_financials(calls)
        assert fin["cash_collected_total"] == 0
        assert fin["valor_total_contrato"] == 0

    def test_exclui_reembolso(self):
        calls = [
            {"houve_venda": True, "venda_revertida": True,
             "cash_collected": 5000, "valor_total": 10000},
        ]
        fin = aggregate_financials(calls)
        assert fin["cash_collected_total"] == 0
