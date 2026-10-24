from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import ChatMemberUpdated, Message

from .. import texts
from ..config import Config
from ..db import Database
from ..keyboards import main_reply

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    await db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    name = message.from_user.first_name or "друг"
    await message.answer(texts.WELCOME.format(name=name), reply_markup=main_reply())


@router.message(Command("help"))
@router.message(F.text == texts.BTN_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP, reply_markup=main_reply())


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database, config: Config) -> None:
    if config.admin_ids and message.from_user.id not in config.admin_ids:
        return
    stats = await db.stats()
    await message.answer(texts.STATS.format(**stats))


@router.my_chat_member()
async def membership(event: ChatMemberUpdated, db: Database) -> None:
    if event.chat.type != "private" or not event.from_user:
        return
    status = event.new_chat_member.status
    await db.set_user_active(event.from_user.id, status in {"member", "administrator", "creator"})
