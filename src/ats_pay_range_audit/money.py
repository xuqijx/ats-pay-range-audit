"""Numeric helpers. Salary text is never scanned for amounts."""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

_NUMERIC_TEXT = re.compile(r"-?\d+(\.\d+)?")
_CURRENCY = re.compile(r"[A-Za-z]{3}")
_PERIOD = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,31}")


def finite_number(value: object) -> int | float | None:
    """Accept JSON numbers and plain numeric strings. Reject booleans and symbols."""

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, str):
        text = value.strip()
        if not _NUMERIC_TEXT.fullmatch(text):
            return None
        if "." in text:
            try:
                number = float(text)
            except ValueError:
                return None
            if not math.isfinite(number):
                return None
            if number.is_integer():
                return int(number)
            return number
        try:
            return int(text)
        except ValueError:
            return None
    return None


def whole_cents(value: object) -> int | None:
    number = finite_number(value)
    if isinstance(number, int):
        return number
    return None


def cents_to_major(cents: int | None) -> int | str | None:
    """Convert integer cents to major units without binary floating point."""

    if cents is None:
        return None
    sign = -1 if cents < 0 else 1
    whole, remainder = divmod(abs(cents), 100)
    major = sign * whole
    if remainder == 0:
        return major
    if sign < 0:
        return f"-{whole}.{remainder:02d}"
    return f"{major}.{remainder:02d}"


def amount(value: object) -> int | str | None:
    """Canonical major-unit amount: int when integral, otherwise a decimal string."""

    number = finite_number(value)
    if number is None:
        return None
    if isinstance(number, int):
        return number
    try:
        decimal = Decimal(str(number))
    except InvalidOperation:
        return None
    if not decimal.is_finite():
        return None
    if decimal == decimal.to_integral_value():
        return int(decimal)
    return format(decimal.normalize(), "f")


def currency_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _CURRENCY.fullmatch(text):
        return None
    return text.upper()


def period_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or _PERIOD.fullmatch(text) is None:
        return None
    return text


def short_text(value: object, limit: int = 240) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = "".join(ch for ch in value if ch == "\t" or ord(ch) >= 32)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return None
    return cleaned[:limit]


def canon_amount(value: object) -> int | str | None:
    """Normalize snapshot amounts so 80000 and 80000.0 compare equal."""

    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        try:
            decimal = Decimal(text)
        except InvalidOperation:
            return None
    else:
        number = finite_number(value)
        if number is None:
            return None
        decimal = Decimal(str(number))
    if not decimal.is_finite():
        return None
    if decimal == decimal.to_integral_value():
        return int(decimal)
    return format(decimal.normalize(), "f")


def range_sort_key(item: dict) -> tuple:
    return (
        item.get("currency") or "",
        item.get("period") or "",
        _amount_key(item.get("min")),
        _amount_key(item.get("max")),
        item.get("label") or "",
        item.get("summary") or "",
        item.get("source") or "",
    )


def _amount_key(value: object) -> tuple:
    canonical = canon_amount(value)
    if canonical is None:
        return (2, "")
    if isinstance(canonical, int):
        return (0, canonical)
    return (1, canonical)


def sort_ranges(ranges: list[dict]) -> list[dict]:
    return sorted(ranges, key=range_sort_key)
