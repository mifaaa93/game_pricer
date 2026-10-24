from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..db import Database
from ..keyboards import my_games_kb
from ..screens import set_nav, show

router = Router()


async def open_my(event: Message | CallbackQuery, db: Database, page: int = 0) -> None:
    user = event.from_user
    if not user:
        return
    games = await db.user_watches(user.id)
    set_nav(user.id, screen="my", my_page=page)
    if not games:
        await show(event, db, "my", texts.MY_EMPTY, my_games_kb([], 0))
        return
    await show(
        event,
        db,
        "my",
        texts.MY_LIST.format(n=len(games)),
        my_games_kb(games, page),
    )


@router.message(F.text == texts.BTN_MY)
async def my_games(message: Message, db: Database) -> None:
    await open_my(message, db)


@router.callback_query(F.data.startswith("my:"))
async def my_page(callback: CallbackQuery, db: Database) -> None:
    page = int(callback.data.split(":")[1])
    await open_my(callback, db, page=page)
    await callback.answer()
