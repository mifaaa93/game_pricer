from __future__ import annotations

import re

_NBSP = dict.fromkeys(map(ord, "\u00a0\u202f\u2009"), " ")
_FREE = {
    "безкоштовно",
    "бесплатно",
    "free",
    "included",
    "долучено",
    "включено",
}
_PRICE_RE = re.compile(
    r"(?:UAH|USD|EUR|GBP|RUB|₴|\$|€)\s*([\d\s]+(?:[.,]\d{1,2})?)",
    re.IGNORECASE,
)
_PLAIN_RE = re.compile(r"([\d\s]+(?:[.,]\d{1,2})?)")
_DISCOUNT_RE = re.compile(r"[-−–—]?\s*(\d+)\s*%")


def parse_price(text: str | None, is_free: bool = False) -> int | None:
    """Store price as integer minor units (kopecks). 329,00 ₴ → 32900."""
    if is_free:
        return 0
    if not text:
        return None
    t = str(text).translate(_NBSP).strip()
    if not t:
        return None
    if t.casefold() in _FREE:
        return 0
    m = _PRICE_RE.search(t) or _PLAIN_RE.search(t)
    if not m:
        return None
    raw = m.group(1).replace(" ", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        if "." in raw:
            major, frac = raw.split(".", 1)
            frac = (frac + "00")[:2]
            return int(major) * 100 + int(frac)
        return int(raw) * 100
    except ValueError:
        return None


def parse_discount(text: str | None) -> int | None:
    if not text:
        return None
    m = _DISCOUNT_RE.search(text.replace("\xa0", " "))
    if not m:
        return None
    return int(m.group(1))


def format_price(value: int | None, currency: str = "₴") -> str:
    if value is None:
        return "н/д"
    if value == 0:
        return "бесплатно"
    major, frac = divmod(abs(value), 100)
    grouped = f"{major:,}".replace(",", " ")
    if frac:
        return f"{grouped},{frac:02d} {currency}"
    return f"{grouped} {currency}"


def price_delta_label(old: int | None, new: int | None) -> str:
    if old is None or new is None:
        return ""
    diff = new - old
    if diff == 0:
        return ""
    sign = "+" if diff > 0 else "−"
    return f"{sign}{format_price(abs(diff))}"
