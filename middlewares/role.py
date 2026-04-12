"""Middleware для проверки ролей пользователей."""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from db.users import get_role

logger = logging.getLogger(__name__)


class RoleMiddleware(BaseMiddleware):
    """Подтягивает роль пользователя из БД и кладёт в data['role']."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user:
            role = await get_role(user.id)
            data["role"] = role or "none"
        else:
            data["role"] = "none"

        return await handler(event, data)
