import pytest
from backend.engine.normalizer import normalize_email, normalize_phone, normalize_money, normalize_date


class TestNormalizeEmail:
    def test_lowercase(self):
        assert normalize_email("JOAO@EMAIL.COM") == "joao@email.com"

    def test_strip_spaces(self):
        assert normalize_email("  joao@email.com  ") == "joao@email.com"

    def test_none(self):
        assert normalize_email(None) is None

    def test_empty(self):
        assert normalize_email("") is None
        assert normalize_email("   ") is None


class TestNormalizePhone:
    def test_remove_ddi_13_digits(self):
        assert normalize_phone("+55 (11) 99999-0000") == "11999990000"

    def test_remove_ddi_already_digits(self):
        assert normalize_phone("5511999990000") == "11999990000"

    def test_already_clean(self):
        assert normalize_phone("11999990000") == "11999990000"

    def test_landline(self):
        assert normalize_phone("(11) 3333-4444") == "1133334444"

    def test_none(self):
        assert normalize_phone(None) is None

    def test_empty(self):
        assert normalize_phone("") is None

    def test_no_ddi_removal_if_not_55(self):
        # número com 13 dígitos mas não começa com 55 — não remove
        assert normalize_phone("13111999990000") == "13111999990000"


class TestNormalizeMoney:
    def test_br_format(self):
        assert normalize_money("R$ 1.500,00") == 1500.0

    def test_us_format(self):
        assert normalize_money("1500.00") == 1500.0

    def test_integer(self):
        assert normalize_money("1500") == 1500.0

    def test_only_comma(self):
        assert normalize_money("1500,00") == 1500.0

    def test_none(self):
        assert normalize_money(None) is None

    def test_empty(self):
        assert normalize_money("") is None


class TestNormalizeDate:
    def test_br_format(self):
        assert normalize_date("15/03/2024") == "2024-03-15"

    def test_iso_passthrough(self):
        assert normalize_date("2024-03-15") == "2024-03-15"

    def test_short_year(self):
        assert normalize_date("15/03/24") == "2024-03-15"

    def test_none(self):
        assert normalize_date(None) is None

    def test_empty(self):
        assert normalize_date("") is None
