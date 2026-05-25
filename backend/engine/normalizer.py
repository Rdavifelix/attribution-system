"""
Normalização de campos de identidade (email, telefone).

Regras:
- email_norm:    strip + lower
- telefone_norm: só dígitos; remove DDI 55 se o número tiver 13 dígitos

Estas funções são compartilhadas entre todos os ingestores (GHL, planilha)
para garantir que as chaves de cruzamento sejam idênticas independente da fonte.
"""
from __future__ import annotations
import re


def normalize_email(raw: str | None) -> str | None:
    """Retorna o email em minúsculas sem espaços, ou None se vazio."""
    if not raw:
        return None
    result = raw.strip().lower()
    return result if result else None


def normalize_phone(raw: str | None) -> str | None:
    """
    Retorna o telefone só com dígitos, sem DDI 55.
    Exemplos:
      '+55 (11) 99999-0000' → '11999990000'
      '5511999990000'       → '11999990000'
      '11999990000'         → '11999990000'
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    # Remove DDI 55 apenas quando resulta em número de 11 ou 10 dígitos (BR)
    if len(digits) == 13 and digits.startswith("55"):
        digits = digits[2:]
    elif len(digits) == 12 and digits.startswith("55"):
        digits = digits[2:]
    return digits if digits else None


def normalize_money(raw: str | None) -> float | None:
    """
    Converte string monetária para float.
    Aceita: 'R$ 1.500,00' | '1500.00' | '1.500,00' | '1500'
    """
    if not raw:
        return None
    # Remove símbolos de moeda e espaços
    s = re.sub(r"[R$\s]", "", str(raw)).strip()
    if not s:
        return None
    # Detecta formato BR (ponto como milhar, vírgula como decimal)
    if "," in s and "." in s:
        # ex: '1.500,00' → '1500.00'
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # ex: '1500,00' → '1500.00'
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def normalize_date(raw: str | None) -> str | None:
    """
    Converte datas no formato DD/MM/YYYY para YYYY-MM-DD (ISO 8601).
    Retorna None se inválido ou vazio.
    """
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    # Já está em ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    # DD/MM/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
    # DD/MM/YY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2})$", s)
    if m:
        d, mo, y = m.groups()
        year = f"20{y}" if int(y) < 50 else f"19{y}"
        return f"{year}-{mo.zfill(2)}-{d.zfill(2)}"
    return None
