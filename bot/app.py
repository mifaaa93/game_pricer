from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault, TelegramObject
from dotenv import load_dotenv

from .collector import Collector
from .config import Config
from .db import Database
from .handlers import setup_routers
from .notifier import Notifier
from .psn import PSNClient

log = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        db = data.get("db")
        if user and db is not None:
            await db.upsert_user(user.id, user.username, user.first_name)
        return await handler(event, data)


def setup_logging(config: Config) -> None:
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
        file_handler = RotatingFileHandler(
            config.log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)


async def run() -> None:
    load_dotenv()
    config = Config.from_env()
    setup_logging(config)

    bot = Bot(token=config.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    db = Database(config.db_path)
    await db.connect()
    psn = PSNClient(locale=config.locale, delay=config.request_delay, page_size=config.page_size)
    await psn.start()

    collector = Collector(db, psn, config)
    notifier = Notifier(bot, db, config)

    root = setup_routers()
    root.message.middleware(UserMiddleware())
    root.callback_query.middleware(UserMiddleware())
    root.inline_query.middleware(UserMiddleware())
    dp.include_router(root)
    dp.workflow_data.update(db=db, config=config)

    @dp.error()
    async def on_error(event) -> None:
        log.error("handler error: %s", event.exception, exc_info=event.exception)

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Меню"),
            BotCommand(command="help", description="Как пользоваться"),
        ],
        scope=BotCommandScopeDefault(),
    )

    tasks = [
        asyncio.create_task(collector.run_forever(), name="collector"),
        asyncio.create_task(notifier.run_forever(), name="notifier"),
    ]
    log.info("bot started, locale=%s", config.locale)
    try:
        await dp.start_polling(bot)
    finally:
        collector.stop()
        notifier.stop()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await psn.close()
        await db.close()
        await bot.session.close()
