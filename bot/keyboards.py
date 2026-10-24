from __future__ import annotations

from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from . import texts
from .formatters import list_button_text

GENRES_PER_PAGE = 12
GAMES_PER_PAGE = 8


def main_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_SEARCH), KeyboardButton(text=texts.BTN_SALE)],
            [KeyboardButton(text=texts.BTN_CATALOG), KeyboardButton(text=texts.BTN_MY)],
            [KeyboardButton(text=texts.BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Поиск или меню…",
    )


def search_inline_kb(query: str = "") -> InlineKeyboardMarkup:
    label = "Найти игру" if not query else f"Искать «{query[:40]}»"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    switch_inline_query_current_chat=query,
                )
            ]
        ]
    )


def platform_kb(prefix: str = "cat") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="PS4", callback_data=f"{prefix}:PS4"),
                InlineKeyboardButton(text="PS5", callback_data=f"{prefix}:PS5"),
            ],
            [InlineKeyboardButton(text="PS4 и PS5", callback_data=f"{prefix}:all")],
        ]
    )


def _pages(total: int, per_page: int) -> int:
    return max(1, (total + per_page - 1) // per_page)


def genre_kb(
    platform: str,
    genres: list[dict[str, Any]],
    page: int = 0,
    source: str = "cat",
) -> InlineKeyboardMarkup:
    extra = [
        InlineKeyboardButton(text="Все игры", callback_data=f"l:{source}:{platform}:ALL:0"),
        InlineKeyboardButton(text="Скидки", callback_data=f"l:{source}:{platform}:SALE:0"),
    ]
    start = page * GENRES_PER_PAGE
    chunk = genres[start : start + GENRES_PER_PAGE]
    rows: list[list[InlineKeyboardButton]] = [extra]
    row: list[InlineKeyboardButton] = []
    for g in chunk:
        label = f"{g['genre_name']} ({g['n']})"
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
        nav.append(InlineKeyboardButton(text="←", callback_data=f"gr:{source}:{platform}:{page-1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="→", callback_data=f"gr:{source}:{platform}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="Платформа", callback_data=f"plat:{source}")])
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
            InlineKeyboardButton(text="←", callback_data=f"l:{source}:{platform}:{genre}:{page-1}")
        )
    if page + 1 < total_pages:
        nav.append(
            InlineKeyboardButton(text="→", callback_data=f"l:{source}:{platform}:{genre}:{page+1}")
        )
    if nav:
        rows.append(nav)
    if source == "sale":
        back = f"plat:sale"
    else:
        back = f"gr:{source}:{platform}:0"
    rows.append([InlineKeyboardButton(text="Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def store_kb(game: dict[str, Any]) -> InlineKeyboardMarkup | None:
    store = game.get("store_url")
    if not store:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="В магазин", url=store)]]
    )


def game_kb(game: dict[str, Any], watching: bool) -> InlineKeyboardMarkup:
    product_id = game["product_id"]
    watch = "★ Слежу" if watching else "☆ Следить"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=watch, callback_data=f"w:{product_id}")],
    ]
    store = game.get("store_url")
    if store:
        rows.append([InlineKeyboardButton(text="В магазин", url=store)])
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
        nav.append(InlineKeyboardButton(text="←", callback_data=f"my:{page-1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="→", callback_data=f"my:{page+1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)
