"""Только коллектор каталога, без Telegram-бота.

Нужен тот же .env (BOT_TOKEN можно любой непустой, он не используется).
Удобно, если бот и сбор цен разнесены по процессам.
"""

from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

from bot.collector import Collector
from bot.config import Config
from bot.db import Database
from bot.psn import PSNClient


async def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    import os

    if not os.getenv("BOT_TOKEN"):
        os.environ["BOT_TOKEN"] = "0:collector"
    config = Config.from_env()
    db = Database(config.db_path)
    await db.connect()
    psn = PSNClient(locale=config.locale, delay=config.request_delay, page_size=config.page_size)
    await psn.start()
    collector = Collector(db, psn, config)
    try:
        await collector.run_forever()
    finally:
        await psn.close()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
