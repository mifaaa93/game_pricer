from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

from .. import texts
from ..db import Database
from ..formatters import game_card
from ..keyboards import GAMES_PER_PAGE, game_kb, games_kb, genre_kb, platform_kb, search_inline_kb
from .watchlist import send_game_card

router = Router()


def _plat_label(platform: str) -> str:
    return texts.PLATFORM_LABEL.get(platform, platform)


async def _ensure_catalog(message: Message, db: Database) -> bool:
    if await db.games_count() == 0:
        await message.answer(texts.EMPTY_CATALOG)
        return False
    return True


@router.message(F.text == texts.BTN_CATALOG)
async def catalog_start(message: Message, db: Database) -> None:
    if not await _ensure_catalog(message, db):
        return
    await message.answer(texts.PICK_PLATFORM, reply_markup=platform_kb("cat"))


@router.message(F.text == texts.BTN_SALE)
async def sale_start(message: Message, db: Database) -> None:
    if not await _ensure_catalog(message, db):
        return
    await message.answer(texts.PICK_PLATFORM, reply_markup=platform_kb("sale"))


@router.callback_query(F.data.startswith("plat:"))
async def pick_platform_screen(callback: CallbackQuery) -> None:
    if not callback.message or not callback.data:
        await callback.answer()
        return
    source = callback.data.split(":", 1)[1]
    await callback.message.edit_text(texts.PICK_PLATFORM, reply_markup=platform_kb(source))
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"))
async def catalog_platform(callback: CallbackQuery, db: Database) -> None:
    platform = callback.data.split(":", 1)[1]
    await _show_genres(callback, db, platform, page=0, source="cat")


@router.callback_query(F.data.startswith("sale:"))
async def sale_platform(callback: CallbackQuery, db: Database) -> None:
    platform = callback.data.split(":", 1)[1]
    await _show_games(callback, db, platform, "SALE", 0, source="sale")


@router.callback_query(F.data.startswith("gr:"))
async def genre_page(callback: CallbackQuery, db: Database) -> None:
    _, source, platform, page_s = callback.data.split(":")
    await _show_genres(callback, db, platform, page=int(page_s), source=source)


@router.callback_query(F.data.startswith("l:"))
async def game_list(callback: CallbackQuery, db: Database) -> None:
    _, source, platform, genre, page_s = callback.data.split(":")
    await _show_games(callback, db, platform, genre, int(page_s), source=source)


@router.callback_query(F.data.startswith("v:"))
async def view_game(callback: CallbackQuery, db: Database) -> None:
    product_id = callback.data.split(":", 1)[1]
    game = await db.get_game(product_id)
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    await send_game_card(callback, db, game)
    await callback.answer()


@router.callback_query(F.data.startswith("w:"))
async def toggle_watch(callback: CallbackQuery, db: Database) -> None:
    product_id = callback.data.split(":", 1)[1]
    game = await db.get_game(product_id)
    if not game or not callback.from_user:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    watching = await db.toggle_watch(callback.from_user.id, product_id)
    history = [] if callback.inline_message_id else await db.history(product_id, limit=3)
    text = game_card(game, watching, history)
    kb = game_kb(game, watching)
    try:
        if callback.inline_message_id:
            await callback.bot.edit_message_text(
                text,
                inline_message_id=callback.inline_message_id,
                reply_markup=kb,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        elif callback.message and callback.message.photo:
            await callback.message.edit_caption(text, reply_markup=kb)
        elif callback.message:
            await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer(texts.WATCH_ON if watching else texts.WATCH_OFF)


@router.message(F.text == texts.BTN_SEARCH)
async def search_button(message: Message, db: Database) -> None:
    if await db.games_count() == 0:
        await message.answer(texts.EMPTY_CATALOG)
        return
    await message.answer(texts.SEARCH_HINT, reply_markup=search_inline_kb())


@router.message(
    F.text
    & ~F.via_bot
    & ~F.text.contains("\n")
    & ~F.text.in_(
        {texts.BTN_CATALOG, texts.BTN_SALE, texts.BTN_MY, texts.BTN_HELP, texts.BTN_SEARCH}
    )
)
async def search_text(message: Message, db: Database) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/") or len(text) > 80:
        return
    if await db.games_count() == 0:
        await message.answer(texts.EMPTY_CATALOG)
        return
    await message.answer(
        texts.SEARCH_HINT,
        reply_markup=search_inline_kb(text),
    )


async def _show_genres(
    callback: CallbackQuery,
    db: Database,
    platform: str,
    page: int,
    source: str,
) -> None:
    if not callback.message:
        await callback.answer()
        return
    plat = None if platform == "all" else platform
    genres = await db.list_genres(plat)
    await callback.message.edit_text(
        texts.PICK_GENRE.format(platform=_plat_label(platform)),
        reply_markup=genre_kb(platform, genres, page, source=source),
    )
    await callback.answer()


async def _show_games(
    callback: CallbackQuery,
    db: Database,
    platform: str,
    genre: str,
    page: int,
    source: str,
) -> None:
    if not callback.message:
        await callback.answer()
        return
    plat = None if platform == "all" else platform
    games, total = await db.browse(plat, genre, page, GAMES_PER_PAGE)
    if total == 0:
        await callback.answer(texts.NO_GAMES, show_alert=True)
        return
    title = await _list_title(db, platform, genre)
    text = texts.GAME_LIST.format(title=title, total=total)
    if total > GAMES_PER_PAGE:
        pages = (total + GAMES_PER_PAGE - 1) // GAMES_PER_PAGE
        text += f"\nстр. {page + 1}/{pages}"
    await callback.message.edit_text(
        text,
        reply_markup=games_kb(platform, genre, games, page, total, source=source),
    )
    await callback.answer()


async def _list_title(db: Database, platform: str, genre: str) -> str:
    plat = _plat_label(platform)
    if genre == "SALE":
        return f"Скидки · {plat}"
    if genre == "ALL":
        return f"Все игры · {plat}"
    genres = await db.list_genres(None if platform == "all" else platform)
    for item in genres:
        if item["genre_key"] == genre:
            return f"{item['genre_name']} · {plat}"
    return f"{genre} · {plat}"
