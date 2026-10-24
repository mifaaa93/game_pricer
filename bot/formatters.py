from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from .price import format_price, price_delta_label

KYIV = ZoneInfo("Europe/Kyiv")
HISTORY_LIMIT = 10

STORE_BASE = "https://store.playstation.com/uk-ua/product/"


def short_name(name: str, limit: int = 36) -> str:
    name = name.strip()
    if len(name) <= limit:
        return name
    return name[: limit - 1] + "…"


def inline_description(game: dict[str, Any]) -> str:
    platforms = ", ".join(game.get("platforms") or []) or "PS"
    price = format_price(game.get("current_price"))
    parts = [platforms, price]
    if game.get("plus_included") and game.get("plus_label"):
        parts.append(str(game["plus_label"]))
    elif game.get("discount_percent"):
        parts.append(f"−{game['discount_percent']}%")
    elif game.get("plus_label"):
        parts.append(str(game["plus_label"]))
    return " · ".join(parts)


def list_button_text(game: dict[str, Any]) -> str:
    name = short_name(game.get("name") or "—")
    price = format_price(game.get("current_price"))
    if game.get("plus_included"):
        return f"Plus · {name} · {price}"
    pct = game.get("discount_percent")
    if pct:
        return f"−{pct}% {name} · {price}"
    return f"{name} · {price}"


def game_card(
    game: dict[str, Any],
    watching: bool,
    history: list[dict[str, Any]] | None = None,
) -> str:
    name = escape(game.get("name") or "—")
    platforms = " · ".join(game.get("platforms") or []) or "PS"
    genres = [
        g.get("genre_name") or g.get("genre_key") or ""
        for g in (game.get("genres") or [])
    ]
    genres = [g for g in genres if g][:3]
    current = game.get("current_price")
    base = game.get("base_price")
    pct = game.get("discount_percent")
    plus_label = game.get("plus_label")
    plus_included = bool(game.get("plus_included"))
    on_sale = (
        not plus_included
        and pct
        and base is not None
        and current is not None
        and base > current
    )

    lines = [f"<b>{name}</b>", escape(platforms)]
    if genres:
        lines.append(f"<i>{escape(' · '.join(genres))}</i>")

    price_now = format_price(current)
    if plus_included:
        extra = f"\n{escape(plus_label)} — в подписке" if plus_label else "\nв подписке"
        lines.append(f"<blockquote><b>{price_now}</b>{extra}</blockquote>")
    elif on_sale:
        saved = format_price(base - current)
        extra = f"\nесть в {escape(plus_label)}" if plus_label else ""
        lines.append(
            "<blockquote>"
            f"−{pct}%\n"
            f"<b>{price_now}</b>\n"
            f"<s>{format_price(base)}</s>  ·  выгода {saved}"
            f"{extra}"
            "</blockquote>"
        )
    elif plus_label:
        lines.append(
            f"<blockquote><b>{price_now}</b>\nесть в {escape(plus_label)}</blockquote>"
        )
    else:
        lines.append(f"<blockquote><b>{price_now}</b></blockquote>")

    if watching:
        lines.append("★ в списке")
    lines.extend(_history_lines(history, current))
    return "\n".join(lines)


def format_history_when(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KYIV).strftime("%d.%m.%y %H:%M")
    except ValueError:
        return str(iso)[:16]


def _history_lines(history: list[dict[str, Any]] | None, current: int | None) -> list[str]:
    if not history:
        return []
    rows = history[:HISTORY_LIMIT]
    lines = ["История цен"]
    prices: list[int] = []
    if current is not None:
        prices.append(current)
    for row in rows:
        price = row.get("price")
        if isinstance(price, int):
            prices.append(price)
        when = format_history_when(row.get("recorded_at"))
        disc = row.get("discount_text") or ""
        extra = f"  {escape(str(disc))}" if disc else ""
        lines.append(f"{escape(when)}  {escape(format_price(price))}{extra}")
    uniq = {p for p in prices if p is not None}
    if len(uniq) >= 2:
        lines.append(f"мин {format_price(min(uniq))} · макс {format_price(max(uniq))}")
    return lines


def store_url(event: dict[str, Any]) -> str | None:
    url = event.get("store_url")
    if url:
        return str(url)
    product_id = event.get("product_id")
    if product_id:
        return f"{STORE_BASE}{product_id}"
    return None


def _linked_name(event: dict[str, Any], limit: int = 48) -> str:
    name = escape(short_name(event.get("name") or event.get("product_id") or "—", limit))
    url = store_url(event)
    if not url:
        return name
    return f'<a href="{escape(url, quote=True)}">{name}</a>'


def change_line(event: dict[str, Any]) -> str:
    name = _linked_name(event)
    old = format_price(event.get("old_price"))
    new = format_price(event.get("new_price"))
    discount = event.get("new_discount") or ""
    extra = f"  {escape(discount)}" if discount else ""
    if event.get("kind") == "new":
        return f"🆕 {name}\n{new}{extra}"
    old_p = event.get("old_price")
    new_p = event.get("new_price")
    if old_p is not None and new_p is not None and new_p < old_p:
        arrow = "📉"
    elif old_p is not None and new_p is not None and new_p > old_p:
        arrow = "📈"
    else:
        arrow = "💱"
    delta = price_delta_label(old_p, new_p)
    tail = f"  ({escape(delta)})" if delta else ""
    return f"{arrow} {name}\n{old} → <b>{new}</b>{extra}{tail}"


def channel_digest(events: list[dict[str, Any]], header: str | None = None) -> list[str]:
    title = header or "PlayStation Store UA — изменения цен"
    chunks: list[str] = []
    buf: list[str] = [f"<b>{escape(title)}</b>"]
    size = len(buf[0])
    for event in events:
        block = change_line(event)
        if size + len(block) + 2 > 3500:
            chunks.append("\n\n".join(buf))
            buf = [f"<b>{escape(title)}</b>"]
            size = len(buf[0])
        buf.append(block)
        size += len(block) + 2
    if len(buf) > 1:
        chunks.append("\n\n".join(buf))
    return chunks


def user_change(event: dict[str, Any]) -> str:
    return "<b>Изменение цены</b>\n" + change_line(event)


def change_headline(event: dict[str, Any]) -> str:
    if event.get("kind") == "new":
        return "🆕 Новая игра в каталоге"
    old_p = event.get("old_price")
    new_p = event.get("new_price")
    if old_p is not None and new_p is not None and new_p < old_p:
        return "📉 Цена упала"
    if old_p is not None and new_p is not None and new_p > old_p:
        return "📈 Цена выросла"
    return "💱 Цена изменилась"


def price_move_line(event: dict[str, Any]) -> str:
    old_p = event.get("old_price")
    new_p = event.get("new_price")
    if old_p is None or new_p is None or old_p == new_p:
        return ""
    discount = event.get("new_discount") or ""
    extra = f"  {escape(discount)}" if discount else ""
    delta = price_delta_label(old_p, new_p)
    tail = f"  ({escape(delta)})" if delta else ""
    return f"{format_price(old_p)} → <b>{format_price(new_p)}</b>{extra}{tail}"


def channel_caption(
    event: dict[str, Any],
    game: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> str:
    head = f"<b>{escape(change_headline(event))}</b>"
    move = price_move_line(event)
    hist = history or []
    for limit in (HISTORY_LIMIT, 6, 3, 0):
        card = game_card(game, watching=False, history=hist[:limit] if limit else None)
        parts = [head]
        if move:
            parts.append(move)
        parts.append(card)
        text = "\n\n".join(parts)
        if len(text) <= 1024:
            return text
    return text[:1020] + "…"
