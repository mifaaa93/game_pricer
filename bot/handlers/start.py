from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message, ReplyKeyboardRemove

from .. import texts
from ..config import Config
from ..db import Database
from ..formatters import game_card
from ..keyboards import game_kb, help_kb, home_kb, search_inline_kb
from ..screens import set_nav, show

router = Router()


async def show_home(event: Message | CallbackQuery, db: Database, name: str | None = None) -> None:
    if isinstance(event, CallbackQuery) and event.from_user:
        name = name or event.from_user.first_name
        user_id = event.from_user.id
    elif isinstance(event, Message) and event.from_user:
        name = name or event.from_user.first_name
        user_id = event.from_user.id
    else:
        return
    set_nav(user_id, screen="home")
    await show(event, db, "home", texts.WELCOME.format(name=name or "друг"), home_kb())


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, command: CommandObject) -> None:
    await db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    try:
        gone = await message.answer("\u2060", reply_markup=ReplyKeyboardRemove())
        await gone.delete()
    except Exception:
        pass
    payload = (command.args or "").strip()
    if payload:
        game = await db.get_game(payload)
        if game:
            watching = await db.is_watching(message.from_user.id, payload)
            history = await db.history(payload, limit=10)
            set_nav(message.from_user.id, screen="game", from_screen="home", product_id=payload)
            await show(
                message,
                db,
                f"cover:{payload}",
                game_card(game, watching, history),
                game_kb(game, watching),
                cover_url=game.get("cover_url"),
            )
            return
    await show_home(message, db)


@router.message(Command("help"))
async def cmd_help(message: Message, db: Database) -> None:
    set_nav(message.from_user.id, screen="help")
    await show(message, db, "help", texts.HELP, help_kb())


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database, config: Config) -> None:
    if config.admin_ids and message.from_user.id not in config.admin_ids:
        return
    stats = await db.stats()
    await show(message, db, "help", texts.STATS.format(**stats), help_kb())


@router.callback_query(F.data.startswith("home:"))
async def home_nav(callback: CallbackQuery, db: Database) -> None:
    action = (callback.data or "home:").split(":", 1)[1]
    if action in {"", "home"}:
        await show_home(callback, db)
        await callback.answer()
        return
    if action == "help":
        set_nav(callback.from_user.id, screen="help")
        await show(callback, db, "help", texts.HELP, help_kb())
        await callback.answer()
        return
    if action == "search":
        set_nav(callback.from_user.id, screen="search")
        await show(callback, db, "search", texts.SEARCH_HINT, search_inline_kb())
        await callback.answer()
        return
    if action == "cat":
        from .browse import open_platforms

        await open_platforms(callback, db, "cat")
        await callback.answer()
        return
    if action == "sale":
        from .browse import open_platforms

        await open_platforms(callback, db, "sale")
        await callback.answer()
        return
    if action == "my":
        from .watchlist import open_my

        await open_my(callback, db)
        await callback.answer()
        return
    await callback.answer()


@router.my_chat_member()
async def membership(event: ChatMemberUpdated, db: Database) -> None:
    if event.chat.type != "private" or not event.from_user:
        return
    status = event.new_chat_member.status
    await db.set_user_active(event.from_user.id, status in {"member", "administrator", "creator"})
