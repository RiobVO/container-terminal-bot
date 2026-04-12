"""Middleware фильтрации чатов: пропускает private + разрешённые группы."""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class ChatFilterMiddleware(BaseMiddleware):
    """Блокирует сообщения из неразрешённых чатов."""

    def __init__(self, group_ids: frozenset[int]) -> None:
        self._group_ids = group_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = None
        if isinstance(event, Message) and event.chat:
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat

        if chat is None:
            return None

        if chat.type == "private":
            return await handler(event, data)

        if chat.type in ("group", "supergroup") and chat.id in self._group_ids:
            return await handler(event, data)

        logger.debug("Чат %s (%s) не в списке разрешённых", chat.id, chat.type)
        return None
