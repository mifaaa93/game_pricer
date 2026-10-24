from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, InputMediaPhoto, Message

from .config import ROOT
from .db import Database

log = logging.getLogger(__name__)

ASSETS = ROOT / "assets" / "menu"

ASSET_FILES = {
    "home": "home.jpg",
    "catalog": "home.jpg",
    "sale": "sale.jpg",
    "ps4": "ps4.jpg",
    "ps5": "ps5.jpg",
    "all": "home.jpg",
    "my": "my.jpg",
    "search": "search.jpg",
    "help": "help.jpg",
    "genre_action": "genre_action.jpg",
    "genre_adventure": "genre_adventure.jpg",
    "genre_rpg": "genre_rpg.jpg",
    "genre_racing": "genre_racing.jpg",
    "genre_horror": "genre_horror.jpg",
    "genre_sports": "genre_sports.jpg",
    "genre_puzzle": "genre_puzzle.jpg",
    "genre_strategy": "genre_strategy.jpg",
    "genre_arcade": "genre_arcade.jpg",
}

GENRE_ASSET = {
    "ACTION": "genre_action",
    "COMBAT": "genre_action",
    "FIGHTING": "genre_action",
    "SHOOTER": "genre_action",
    "FIRST_PERSON_SHOOTER": "genre_action",
    "ADVENTURE": "genre_adventure",
    "OPEN_WORLD": "genre_adventure",
    "STORY_RICH": "genre_adventure",
    "ROLE_PLAYING_GAMES": "genre_rpg",
    "FANTASY": "genre_rpg",
    "RACING": "genre_racing",
    "HORROR": "genre_horror",
    "SURVIVAL": "genre_horror",
    "STEALTH": "genre_horror",
    "SPORTS": "genre_sports",
    "FITNESS": "genre_sports",
    "PUZZLE": "genre_puzzle",
    "QUIZ": "genre_puzzle",
    "BOARD": "genre_puzzle",
    "CARD": "genre_puzzle",
    "STRATEGY": "genre_strategy",
    "SIMULATION": "genre_strategy",
    "TACTICAL": "genre_strategy",
    "ARCADE": "genre_arcade",
    "CASUAL": "genre_arcade",
    "PLATFORMER": "genre_arcade",
    "PARTY": "genre_arcade",
    "FAMILY": "genre_arcade",
    "SALE": "sale",
    "ALL": "catalog",
}

_NAV: dict[int, dict[str, Any]] = {}
_MSG: dict[int, tuple[int, int]] = {}


def set_nav(user_id: int, **data: Any) -> None:
    _NAV[user_id] = data


def get_nav(user_id: int) -> dict[str, Any]:
    return _NAV.get(user_id) or {}


def last_message(user_id: int) -> tuple[int, int] | None:
    return _MSG.get(user_id)


def remember_message(user_id: int, chat_id: int, message_id: int) -> None:
    _MSG[user_id] = (chat_id, message_id)


def asset_key_for_genre(genre: str, platform: str | None = None) -> str:
    if genre in GENRE_ASSET:
        return GENRE_ASSET[genre]
    if platform == "PS4":
        return "ps4"
    if platform == "PS5":
        return "ps5"
    return "catalog"


def asset_path(key: str) -> Path:
    name = ASSET_FILES.get(key) or ASSET_FILES["home"]
    path = ASSETS / name
    if path.exists():
        return path
    return ASSETS / "home.jpg"


async def show(
    event: Message | CallbackQuery,
    db: Database,
    asset_key: str,
    caption: str,
    markup: InlineKeyboardMarkup | None,
    cover_url: str | None = None,
) -> Message | None:
    if isinstance(event, CallbackQuery):
        if not event.from_user:
            return None
        user_id = event.from_user.id
        chat = event.message.chat if event.message else None
        chat_id = chat.id if chat else user_id
        bot = event.bot
    else:
        if not event.from_user:
            return None
        user_id = event.from_user.id
        chat_id = event.chat.id
        bot = event.bot
    return await render(
        bot, db, user_id, chat_id, asset_key, caption, markup, cover_url=cover_url
    )


async def _source(db: Database, key: str, url: str | None = None) -> str | FSInputFile:
    cached = await db.get_media(key)
    if cached:
        return cached
    if url:
        return url
    return FSInputFile(asset_path(key))


async def _cache(db: Database, key: str, message: Message | None) -> None:
    if message and message.photo:
        await db.set_media(key, message.photo[-1].file_id)


async def render(
    bot: Bot,
    db: Database,
    user_id: int,
    chat_id: int,
    asset_key: str,
    caption: str,
    markup: InlineKeyboardMarkup | None,
    cover_url: str | None = None,
) -> Message | None:
    src = await _source(db, asset_key, cover_url)
    media = InputMediaPhoto(media=src, caption=caption, parse_mode=ParseMode.HTML)
    last = _MSG.get(user_id)
    if last:
        try:
            msg = await bot.edit_message_media(
                media=media,
                chat_id=last[0],
                message_id=last[1],
                reply_markup=markup,
            )
            if isinstance(msg, Message):
                await _cache(db, asset_key, msg)
                remember_message(user_id, msg.chat.id, msg.message_id)
                return msg
        except TelegramBadRequest as exc:
            log.debug("edit_media failed: %s", exc)
            if "file" in str(exc).lower() or "wrong file" in str(exc).lower():
                await db.drop_media(asset_key)
                src = await _source(db, asset_key, cover_url)
    try:
        msg = await bot.send_photo(chat_id, photo=src, caption=caption, reply_markup=markup)
    except TelegramBadRequest:
        await db.drop_media(asset_key)
        fallback = cover_url or FSInputFile(asset_path(asset_key if not cover_url else "home"))
        try:
            msg = await bot.send_photo(
                chat_id, photo=fallback, caption=caption, reply_markup=markup
            )
        except TelegramBadRequest:
            log.exception("send_photo failed key=%s", asset_key)
            msg = await bot.send_message(chat_id, caption, reply_markup=markup)
            remember_message(user_id, msg.chat.id, msg.message_id)
            return msg
    await _cache(db, asset_key, msg)
    remember_message(user_id, msg.chat.id, msg.message_id)
    return msg
