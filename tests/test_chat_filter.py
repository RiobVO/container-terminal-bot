"""Тесты ChatFilterMiddleware."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import Message, Chat

from middlewares.chat_filter import ChatFilterMiddleware


@pytest.fixture
def middleware():
    return ChatFilterMiddleware(group_ids=frozenset({-100123}))


def _make_message(chat_type: str, chat_id: int = 0) -> MagicMock:
    # Chat создаём без spec — нужны только .type и .id
    chat = MagicMock()
    chat.type = chat_type
    chat.id = chat_id

    # spec=Message обеспечивает isinstance(event, Message) == True,
    # а chat передаём через configure_mock после создания объекта
    msg = MagicMock(spec=Message)
    # Обходим ограничение spec: присваиваем через __dict__ базового mock-а
    type(msg).chat = MagicMock(return_value=chat)
    msg.chat = chat
    return msg


async def test_private_allowed(middleware):
    """Private-чат всегда пропускается."""
    handler = AsyncMock()
    event = _make_message("private")
    await middleware(handler, event, {})
    handler.assert_called_once()


async def test_allowed_group(middleware):
    """Разрешённая группа пропускается."""
    handler = AsyncMock()
    event = _make_message("supergroup", chat_id=-100123)
    await middleware(handler, event, {})
    handler.assert_called_once()


async def test_unknown_group_blocked(middleware):
    """Неразрешённая группа блокируется."""
    handler = AsyncMock()
    event = _make_message("supergroup", chat_id=-100999)
    await middleware(handler, event, {})
    handler.assert_not_called()


async def test_unauthorized_channel_blocked(middleware):
    """Канал не в списке разрешённых — блокируется."""
    handler = AsyncMock()
    event = _make_message("channel", chat_id=-100555)
    await middleware(handler, event, {})
    handler.assert_not_called()


async def test_authorized_channel_allowed(middleware):
    """Канал в списке разрешённых — пропускается (для callback из канала)."""
    handler = AsyncMock()
    event = _make_message("channel", chat_id=-100123)
    await middleware(handler, event, {})
    handler.assert_called_once()
