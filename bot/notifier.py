from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from .config import Config
from .db import Database
from .formatters import channel_digest, game_card, user_change
from .keyboards import game_kb

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot, db: Database, config: Config) -> None:
        self.bot = bot
        self.db = db
        self.config = config
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                await self.flush()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("notifier flush failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=20)
            except asyncio.TimeoutError:
                pass

    async def flush(self) -> None:
        await self._flush_channel()
        await self._flush_users()

    async def _send(
        self,
        chat_id: int,
        text: str,
        photo: str | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        for _ in range(3):
            try:
                if photo:
                    try:
                        caption = text if len(text) <= 1024 else text[:1020] + "…"
                        await self.bot.send_photo(
                            chat_id, photo, caption=caption, reply_markup=reply_markup
                        )
                        return
                    except TelegramBadRequest:
                        photo = None
                        continue
                await self.bot.send_message(
                    chat_id, text, disable_web_page_preview=True, reply_markup=reply_markup
                )
                return
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramForbiddenError:
                if chat_id > 0:
                    await self.db.set_user_active(chat_id, False)
                return
            except TelegramBadRequest as exc:
                log.warning("telegram bad request chat=%s: %s", chat_id, exc)
                return

    async def _flush_channel(self) -> None:
        if not self.config.channel_id:
            events = await self.db.pending_events("notified_channel", limit=500)
            if events:
                await self.db.mark_events([e["id"] for e in events], "notified_channel")
            return
        events = await self.db.pending_events("notified_channel", limit=200)
        if not events:
            return
        changes = [e for e in events if e.get("kind") != "new"]
        news = [e for e in events if e.get("kind") == "new"]
        messages: list[str] = []
        if changes:
            messages.extend(channel_digest(changes))
        if news:
            shown = news[:25]
            extra = len(news) - len(shown)
            header = "PlayStation Store UA — новые игры"
            messages.extend(channel_digest(shown, header=header))
            if extra > 0:
                messages[-1] += f"\n\nещё {extra} новых игр в каталоге"
        for text in messages:
            await self._send(self.config.channel_id, text)
        await self.db.mark_events([e["id"] for e in events], "notified_channel")
        log.info("channel: %s events", len(events))

    async def _flush_users(self) -> None:
        events = await self.db.pending_events("notified_users", limit=100)
        if not events:
            return
        sent = 0
        for event in events:
            if event.get("kind") == "new":
                continue
            user_ids = await self.db.watchers(event["product_id"])
            if not user_ids:
                continue
            game = await self.db.get_game(event["product_id"])
            history = await self.db.history(event["product_id"], limit=5) if game else []
            for user_id in user_ids:
                if game:
                    text = user_change(event) + "\n\n" + game_card(game, watching=True, history=history)
                    await self._send(
                        user_id,
                        text,
                        photo=game.get("cover_url"),
                        reply_markup=game_kb(game, True),
                    )
                else:
                    await self._send(user_id, user_change(event))
                sent += 1
        await self.db.mark_events([e["id"] for e in events], "notified_users")
        if sent:
            log.info("dm: %s messages", sent)
