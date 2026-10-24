from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

from .. import texts
from ..db import Database
from ..formatters import game_card
from ..keyboards import (
    GAMES_PER_PAGE,
    game_kb,
    games_kb,
    genre_kb,
    platform_kb,
    search_inline_kb,
)
from ..screens import asset_key_for_genre, get_nav, set_nav, show

router = Router()


def _plat_label(platform: str) -> str:
    return texts.PLATFORM_LABEL.get(platform, platform)


async def _ensure_catalog(event: Message | CallbackQuery, db: Database) -> bool:
    if await db.games_count() == 0:
        await show(event, db, "catalog", texts.EMPTY_CATALOG, platform_kb("cat"))
        return False
    return True


async def open_platforms(event: Message | CallbackQuery, db: Database, source: str) -> None:
    if not await _ensure_catalog(event, db):
        return
    user_id = event.from_user.id if event.from_user else 0
    set_nav(user_id, screen="plat", source=source)
    asset = "sale" if source == "sale" else "catalog"
    await show(event, db, asset, texts.PICK_PLATFORM, platform_kb(source))


@router.message(F.text == texts.BTN_CATALOG)
async def catalog_start(message: Message, db: Database) -> None:
    await open_platforms(message, db, "cat")


@router.message(F.text == texts.BTN_SALE)
async def sale_start(message: Message, db: Database) -> None:
    await open_platforms(message, db, "sale")


@router.message(F.text == texts.BTN_HELP)
async def help_text(message: Message, db: Database) -> None:
    from .start import cmd_help

    await cmd_help(message, db)


@router.message(F.text == texts.BTN_SEARCH)
async def search_button(message: Message, db: Database) -> None:
    if await db.games_count() == 0:
        await show(message, db, "search", texts.EMPTY_CATALOG, search_inline_kb())
        return
    set_nav(message.from_user.id, screen="search")
    await show(message, db, "search", texts.SEARCH_HINT, search_inline_kb())


@router.callback_query(F.data.startswith("plat:"))
async def pick_platform_screen(callback: CallbackQuery, db: Database) -> None:
    if not callback.data:
        await callback.answer()
        return
    source = callback.data.split(":", 1)[1]
    await open_platforms(callback, db, source)
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
    if not await _open_game(callback, db, product_id):
        await callback.answer("Игра не найдена", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("gv:"))
async def game_step(callback: CallbackQuery, db: Database) -> None:
    nav = get_nav(callback.from_user.id)
    step = -1 if (callback.data or "").endswith("prev") else 1
    index = int(nav.get("index") or 0) + step
    total = int(nav.get("total") or 0)
    if total <= 0:
        await callback.answer()
        return
    index = max(0, min(index, total - 1))
    if nav.get("from_screen") == "my":
        product_id, total = await db.watch_at(callback.from_user.id, index)
    else:
        plat = None if nav.get("platform") in {None, "all"} else nav.get("platform")
        product_id, total = await db.browse_at(plat, nav.get("genre") or "ALL", index)
    if not product_id:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    if not await _open_game(callback, db, product_id, index=index, total=total):
        await callback.answer("Игра не найдена", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data == "nav:back")
async def nav_back(callback: CallbackQuery, db: Database) -> None:
    nav = get_nav(callback.from_user.id)
    prev = nav.get("from_screen")
    if prev == "my":
        from .watchlist import open_my

        await open_my(callback, db, page=int(nav.get("my_page") or 0))
    elif prev == "list" or nav.get("genre"):
        await _show_games(
            callback,
            db,
            nav.get("platform") or "all",
            nav.get("genre") or "ALL",
            int(nav.get("page") or 0),
            source=nav.get("source") or "cat",
        )
    else:
        from .start import show_home

        await show_home(callback, db)
    await callback.answer()


@router.callback_query(F.data.startswith("w:"))
async def toggle_watch(callback: CallbackQuery, db: Database) -> None:
    product_id = callback.data.split(":", 1)[1]
    game = await db.get_game(product_id)
    if not game or not callback.from_user:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    watching = await db.toggle_watch(callback.from_user.id, product_id)
    history = await db.history(product_id, limit=10)
    text = game_card(game, watching, history)
    nav = get_nav(callback.from_user.id)
    kb = game_kb(
        game,
        watching,
        back=not bool(callback.inline_message_id),
        index=nav.get("index"),
        total=nav.get("total"),
    )
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
        await show(message, db, "search", texts.EMPTY_CATALOG, search_inline_kb())
        return
    set_nav(message.from_user.id, screen="search")
    await show(message, db, "search", texts.SEARCH_HINT, search_inline_kb(text))


async def _open_game(
    callback: CallbackQuery,
    db: Database,
    product_id: str,
    index: int | None = None,
    total: int | None = None,
) -> bool:
    game = await db.get_game(product_id)
    if not game or not callback.from_user:
        return False
    nav = get_nav(callback.from_user.id)
    from_screen = nav.get("screen")
    if from_screen == "game":
        from_screen = nav.get("from_screen")
    if index is None or total is None:
        index, total = await _index_in_list(db, callback.from_user.id, product_id, nav)
    set_nav(
        callback.from_user.id,
        screen="game",
        source=nav.get("source", "cat"),
        platform=nav.get("platform", "all"),
        genre=nav.get("genre", "ALL"),
        page=nav.get("page", 0),
        genre_page=nav.get("genre_page", 0),
        from_screen=from_screen,
        my_page=nav.get("my_page", 0),
        product_id=product_id,
        index=index,
        total=total,
    )
    watching = await db.is_watching(callback.from_user.id, product_id)
    history = await db.history(product_id, limit=10)
    text = game_card(game, watching, history)
    await show(
        callback,
        db,
        f"cover:{product_id}",
        text,
        game_kb(game, watching, index=index, total=total),
        cover_url=game.get("cover_url"),
    )
    return True


async def _index_in_list(
    db: Database, user_id: int, product_id: str, nav: dict
) -> tuple[int, int]:
    if nav.get("screen") == "my" or nav.get("from_screen") == "my":
        games = await db.user_watches(user_id)
        ids = [g["product_id"] for g in games]
        try:
            return ids.index(product_id), len(ids)
        except ValueError:
            return 0, len(ids)
    plat = None if nav.get("platform") in {None, "all"} else nav.get("platform")
    genre = nav.get("genre") or "ALL"
    page = int(nav.get("page") or 0)
    games, total = await db.browse(plat, genre, page, GAMES_PER_PAGE)
    try:
        pos = next(i for i, g in enumerate(games) if g["product_id"] == product_id)
    except StopIteration:
        pos = 0
    return page * GAMES_PER_PAGE + pos, total


async def _show_genres(
    callback: CallbackQuery,
    db: Database,
    platform: str,
    page: int,
    source: str,
) -> None:
    plat = None if platform == "all" else platform
    genres = await db.list_genres(plat)
    set_nav(
        callback.from_user.id,
        screen="genres",
        source=source,
        platform=platform,
        genre_page=page,
    )
    asset = "ps4" if platform == "PS4" else "ps5" if platform == "PS5" else "catalog"
    await show(
        callback,
        db,
        asset,
        texts.PICK_GENRE.format(platform=_plat_label(platform)),
        genre_kb(platform, genres, page, source=source),
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
    plat = None if platform == "all" else platform
    games, total = await db.browse(plat, genre, page, GAMES_PER_PAGE)
    if total == 0:
        await callback.answer(texts.NO_GAMES, show_alert=True)
        return
    title = await _list_title(db, platform, genre)
    text = texts.GAME_LIST.format(title=title, total=total)
    if total > GAMES_PER_PAGE:
        pages = (total + GAMES_PER_PAGE - 1) // GAMES_PER_PAGE
        text += f"\n📄 {page + 1}/{pages}"
    set_nav(
        callback.from_user.id,
        screen="list",
        source=source,
        platform=platform,
        genre=genre,
        page=page,
        genre_page=get_nav(callback.from_user.id).get("genre_page", 0),
    )
    asset = asset_key_for_genre(genre, platform)
    await show(
        callback,
        db,
        asset,
        text,
        games_kb(platform, genre, games, page, total, source=source),
    )
    await callback.answer()


async def _list_title(db: Database, platform: str, genre: str) -> str:
    plat = _plat_label(platform)
    emoji = texts.GENRE_EMOJI.get(genre, "🎮")
    if genre == "SALE":
        return f"🔥 Скидки · {plat}"
    if genre == "ALL":
        return f"📚 Все игры · {plat}"
    genres = await db.list_genres(None if platform == "all" else platform)
    for item in genres:
        if item["genre_key"] == genre:
            return f"{emoji} {item['genre_name']} · {plat}"
    return f"{emoji} {genre} · {plat}"
