"""PlayStation Store UA — коллектор цен + Telegram-бот.

Запуск:
  1. Скопируй .env.example в .env, вставь BOT_TOKEN и CHANNEL_ID
  2. pip install -r requirements.txt
  3. python main.py
"""

from __future__ import annotations

import asyncio

from bot.app import run


if __name__ == "__main__":
    asyncio.run(run())
