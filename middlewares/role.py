"""Middleware для проверки ролей пользователей."""
import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from db.users import get_role

logger = logging.getLogger(__name__)

# Кэш ролей в памяти. Ключ — tg_id, значение — (role, expires_at).
# Раньше middleware дёргал БД на КАЖДОЕ сообщение и колбэк (5 быстрых
# тапов = 5 SELECT). Роль меняется крайне редко, кэш на минуту даёт
# мгновенный ответ для всех последующих апдейтов одного юзера.
_ROLE_CACHE: dict[int, tuple[str, float]] = {}
_ROLE_TTL_SECONDS = 60.0


def invalidate_role_cache(tg_id: int | None = None) -> None:
    """Сбрасывает кэш роли (целиком или для одного юзера).

    Вызывать из мест, где роль меняется (set_role в админке), иначе
    юзер будет видеть старую роль до 60 секунд после изменения.
    """
    if tg_id is None:
        _ROLE_CACHE.clear()
    else:
        _ROLE_CACHE.pop(tg_id, None)


async def get_role_cached(tg_id: int) -> str:
    """Возвращает роль с кэшем по TTL.

    Используется и middleware, и хэндлерами (например, отрисовка
    карточки контейнера) — без кэша каждое второе действие юзера
    стрелято бы лишним SELECT в users.
    """
    now = time.monotonic()
    cached = _ROLE_CACHE.get(tg_id)
    if cached is not None and cached[1] > now:
        return cached[0]
    role = await get_role(tg_id)
    role = role or "none"
    _ROLE_CACHE[tg_id] = (role, now + _ROLE_TTL_SECONDS)
    return role


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
            data["role"] = await get_role_cached(user.id)
        else:
            data["role"] = "none"

        return await handler(event, data)
