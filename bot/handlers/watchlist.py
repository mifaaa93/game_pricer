from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

from .. import texts
from ..db import Database
from ..formatters import game_card
from ..keyboards import game_kb, my_games_kb

router = Router()


@router.message(F.text == texts.BTN_MY)
async def my_games(message: Message, db: Database) -> None:
    games = await db.user_watches(message.from_user.id)
    if not games:
        await message.answer(texts.MY_EMPTY)
        return
    await message.answer(
        f"Ты следишь за {len(games)} играми.",
        reply_markup=my_games_kb(games, 0),
    )


@router.callback_query(F.data.startswith("my:"))
async def my_page(callback: CallbackQuery, db: Database) -> None:
    page = int(callback.data.split(":")[1])
    games = await db.user_watches(callback.from_user.id)
    if not callback.message:
        await callback.answer()
        return
    if not games:
        await callback.message.edit_text(texts.MY_EMPTY)
        await callback.answer()
        return
    await callback.message.edit_text(
        f"Ты следишь за {len(games)} играми.",
        reply_markup=my_games_kb(games, page),
    )
    await callback.answer()


def _preview(game: dict) -> LinkPreviewOptions | None:
    url = game.get("store_url") or game.get("cover_url")
    if not url:
        return None
    return LinkPreviewOptions(
        url=url,
        prefer_large_media=True,
        show_above_text=True,
    )


async def send_game_card(callback: CallbackQuery, db: Database, game: dict) -> None:
    watching = await db.is_watching(callback.from_user.id, game["product_id"])
    history = await db.history(game["product_id"], limit=10)
    text = game_card(game, watching, history)
    kb = game_kb(game, watching)
    if not callback.message:
        await callback.answer()
        return
    cover = game.get("cover_url")
    if cover:
        try:
            await callback.message.answer_photo(cover, caption=text, reply_markup=kb)
            return
        except TelegramBadRequest:
            pass
    await callback.message.answer(
        text,
        reply_markup=kb,
        link_preview_options=_preview(game),
    )
