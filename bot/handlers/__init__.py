from aiogram import F, Router
from aiogram.types import CallbackQuery

from . import browse, inline, start, watchlist


def _private_or_inline(callback: CallbackQuery) -> bool:
    if callback.inline_message_id:
        return True
    chat = callback.message.chat if callback.message else None
    return bool(chat and chat.type == "private")


def setup_routers() -> Router:
    root = Router()
    root.message.filter(F.chat.type == "private")
    root.callback_query.filter(_private_or_inline)
    root.include_router(start.router)
    root.include_router(browse.router)
    root.include_router(watchlist.router)
    root.include_router(inline.router)
    return root
