"""Тесты services.group_notify."""
import pytest
from unittest.mock import AsyncMock

from services.group_notify import notify_groups


async def test_notify_sends_to_all_groups():
    """Сообщение отправляется во все группы."""
    bot = AsyncMock()
    await notify_groups(bot, frozenset({-1, -2}), "test")
    assert bot.send_message.call_count == 2


async def test_notify_error_does_not_raise():
    """Ошибка в одной группе не ломает отправку в другие."""
    bot = AsyncMock()
    bot.send_message.side_effect = [Exception("fail"), None]
    await notify_groups(bot, frozenset({-1, -2}), "test")
    assert bot.send_message.call_count == 2


async def test_notify_empty_groups():
    """Пустой список групп — ничего не отправляется."""
    bot = AsyncMock()
    await notify_groups(bot, frozenset(), "test")
    bot.send_message.assert_not_called()
