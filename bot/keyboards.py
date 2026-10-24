from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import texts
from .formatters import list_button_text

GENRES_PER_PAGE = 12
GAMES_PER_PAGE = 8


def _pages(total: int, per_page: int) -> int:
    return max(1, (total + per_page - 1) // per_page)


def home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_SEARCH, callback_data="home:search")],
            [
                InlineKeyboardButton(text=texts.BTN_SALE, callback_data="home:sale"),
                InlineKeyboardButton(text=texts.BTN_CATALOG, callback_data="home:cat"),
            ],
            [
                InlineKeyboardButton(text=texts.BTN_MY, callback_data="home:my"),
                InlineKeyboardButton(text=texts.BTN_HELP, callback_data="home:help"),
            ],
        ]
    )


def search_inline_kb(query: str = "", back: bool = True) -> InlineKeyboardMarkup:
    label = "🔍 Найти игру" if not query else f"🔍 Искать «{query[:32]}»"
    rows = [
        [InlineKeyboardButton(text=label, switch_inline_query_current_chat=query)],
    ]
    if back:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="home:")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def platform_kb(prefix: str = "cat") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔵 PS4", callback_data=f"{prefix}:PS4"),
                InlineKeyboardButton(text="⚪ PS5", callback_data=f"{prefix}:PS5"),
            ],
            [InlineKeyboardButton(text="🎮 PS4 и PS5", callback_data=f"{prefix}:all")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home:")],
        ]
    )


def genre_kb(
    platform: str,
    genres: list[dict[str, Any]],
    page: int = 0,
    source: str = "cat",
) -> InlineKeyboardMarkup:
    extra = [
        InlineKeyboardButton(text="📚 Все игры", callback_data=f"l:{source}:{platform}:ALL:0"),
        InlineKeyboardButton(text="🔥 Скидки", callback_data=f"l:{source}:{platform}:SALE:0"),
    ]
    start = page * GENRES_PER_PAGE
    chunk = genres[start : start + GENRES_PER_PAGE]
    rows: list[list[InlineKeyboardButton]] = [extra]
    row: list[InlineKeyboardButton] = []
    for g in chunk:
        emoji = texts.GENRE_EMOJI.get(g["genre_key"], "🎲")
        label = f"{emoji} {g['genre_name']} ({g['n']})"
        row.append(
            InlineKeyboardButton(
                text=label[:64],
                callback_data=f"l:{source}:{platform}:{g['genre_key']}:0",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav: list[InlineKeyboardButton] = []
    total_pages = _pages(len(genres), GENRES_PER_PAGE)
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"gr:{source}:{platform}:{page-1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"gr:{source}:{platform}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"plat:{source}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def games_kb(
    platform: str,
    genre: str,
    games: list[dict[str, Any]],
    page: int,
    total: int,
    source: str = "cat",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=list_button_text(g), callback_data=f"v:{g['product_id']}")]
        for g in games
    ]
    nav: list[InlineKeyboardButton] = []
    total_pages = _pages(total, GAMES_PER_PAGE)
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"l:{source}:{platform}:{genre}:{page-1}")
        )
    if page + 1 < total_pages:
        nav.append(
            InlineKeyboardButton(text="➡️", callback_data=f"l:{source}:{platform}:{genre}:{page+1}")
        )
    if nav:
        rows.append(nav)
    if source == "sale":
        back = "plat:sale"
    else:
        back = f"gr:{source}:{platform}:0"
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def store_kb(game: dict[str, Any]) -> InlineKeyboardMarkup | None:
    store = game.get("store_url")
    if not store:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🛒 В магазин", url=store)]]
    )


def game_kb(
    game: dict[str, Any],
    watching: bool,
    back: bool = True,
    index: int | None = None,
    total: int | None = None,
) -> InlineKeyboardMarkup:
    product_id = game["product_id"]
    watch = "⭐ Слежу" if watching else "☆ Следить"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=watch, callback_data=f"w:{product_id}")],
    ]
    store = game.get("store_url")
    if store:
        rows.append([InlineKeyboardButton(text="🛒 В магазин", url=store)])
    if index is not None and total is not None and total > 1:
        pager: list[InlineKeyboardButton] = []
        if index > 0:
            pager.append(InlineKeyboardButton(text="⬅️ Пред", callback_data="gv:prev"))
        pager.append(
            InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="noop")
        )
        if index + 1 < total:
            pager.append(InlineKeyboardButton(text="След ➡️", callback_data="gv:next"))
        rows.append(pager)
    if back:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_games_kb(games: list[dict[str, Any]], page: int = 0) -> InlineKeyboardMarkup:
    start = page * GAMES_PER_PAGE
    chunk = games[start : start + GAMES_PER_PAGE]
    rows = [
        [InlineKeyboardButton(text=list_button_text(g), callback_data=f"v:{g['product_id']}")]
        for g in chunk
    ]
    nav: list[InlineKeyboardButton] = []
    total_pages = _pages(len(games), GAMES_PER_PAGE)
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"my:{page-1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"my:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="home:")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="home:")]]
    )
