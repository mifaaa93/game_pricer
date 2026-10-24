from __future__ import annotations

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    LinkPreviewOptions,
)

from .. import texts
from ..db import Database
from ..formatters import game_card, inline_description
from ..keyboards import game_kb
from ..psn import thumb_url

router = Router()

PAGE = 20


def _result(game: dict, watching: bool) -> InlineQueryResultArticle:
    text = game_card(game, watching)
    kb = game_kb(game, watching)
    thumb = thumb_url(game.get("cover_url"))
    payload: dict = {
        "id": game["product_id"][:64],
        "title": game.get("name") or "—",
        "description": inline_description(game),
        "input_message_content": InputTextMessageContent(
            message_text=text,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        ),
        "reply_markup": kb,
    }
    if thumb:
        payload["thumbnail_url"] = thumb
        payload["thumbnail_width"] = 160
        payload["thumbnail_height"] = 160
    return InlineQueryResultArticle(**payload)


@router.chosen_inline_result()
async def _chosen(_: ChosenInlineResult) -> None:
    return


@router.inline_query()
async def inline_search(query: InlineQuery, db: Database) -> None:
    if await db.games_count() == 0:
        await query.answer(
            [
                InlineQueryResultArticle(
                    id="empty",
                    title=texts.INLINE_EMPTY_TITLE,
                    description=texts.INLINE_EMPTY_DESC,
                    input_message_content=InputTextMessageContent(
                        message_text=texts.EMPTY_CATALOG
                    ),
                )
            ],
            cache_time=10,
            is_personal=True,
        )
        return

    try:
        offset = int(query.offset or 0)
    except ValueError:
        offset = 0

    rows = await db.search(query.query, limit=PAGE + 1, offset=offset)
    has_more = len(rows) > PAGE
    rows = rows[:PAGE]

    user_id = query.from_user.id if query.from_user else 0
    watched = await db.watching_ids(user_id, [g["product_id"] for g in rows]) if user_id else set()
    results = [_result(game, game["product_id"] in watched) for game in rows]

    await query.answer(
        results,
        cache_time=0,
        is_personal=True,
        next_offset=str(offset + PAGE) if has_more else "",
    )
