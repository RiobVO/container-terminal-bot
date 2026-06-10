"""Тесты RoleMiddleware."""
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import CallbackQuery, Message

from middlewares.role import RoleMiddleware


def _make_message(user_id: int | None = 42) -> MagicMock:
    """Message-событие; user_id=None — сообщение без from_user."""
    msg = MagicMock(spec=Message)
    if user_id is None:
        msg.from_user = None
    else:
        user = MagicMock()
        user.id = user_id
        msg.from_user = user
    return msg


def _make_callback(user_id: int = 42) -> MagicMock:
    cq = MagicMock(spec=CallbackQuery)
    user = MagicMock()
    user.id = user_id
    cq.from_user = user
    return cq


async def test_message_role_from_db():
    """Роль из БД кладётся в data['role'] для Message."""
    handler = AsyncMock(return_value="handled")
    data: dict = {}
    event = _make_message()
    with patch(
        "middlewares.role.get_role", new=AsyncMock(return_value="operator")
    ) as get_role:
        result = await RoleMiddleware()(handler, event, data)

    get_role.assert_awaited_once_with(42)
    assert data["role"] == "operator"
    handler.assert_awaited_once_with(event, data)
    assert result == "handled"


async def test_message_unknown_user_gets_none_role():
    """Пользователь без записи в БД получает роль 'none'."""
    handler = AsyncMock()
    data: dict = {}
    with patch("middlewares.role.get_role", new=AsyncMock(return_value=None)):
        await RoleMiddleware()(handler, _make_message(), data)

    assert data["role"] == "none"
    handler.assert_awaited_once()


async def test_callback_role_from_db():
    """Роль подтягивается и для CallbackQuery."""
    handler = AsyncMock()
    data: dict = {}
    with patch(
        "middlewares.role.get_role", new=AsyncMock(return_value="full")
    ) as get_role:
        await RoleMiddleware()(handler, _make_callback(user_id=7), data)

    get_role.assert_awaited_once_with(7)
    assert data["role"] == "full"


async def test_message_without_from_user():
    """Message без from_user — роль 'none', БД не трогаем."""
    handler = AsyncMock()
    data: dict = {}
    with patch("middlewares.role.get_role", new=AsyncMock()) as get_role:
        await RoleMiddleware()(handler, _make_message(user_id=None), data)

    get_role.assert_not_awaited()
    assert data["role"] == "none"
    handler.assert_awaited_once()


async def test_unknown_event_type():
    """Событие не Message и не CallbackQuery — роль 'none'."""
    handler = AsyncMock()
    data: dict = {}
    with patch("middlewares.role.get_role", new=AsyncMock()) as get_role:
        await RoleMiddleware()(handler, MagicMock(), data)

    get_role.assert_not_awaited()
    assert data["role"] == "none"
    handler.assert_awaited_once()
