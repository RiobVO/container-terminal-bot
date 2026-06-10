"""Тесты handlers/start.py: команды, fallback-роутер, error handler.

_cfg создаётся на import-time из env — подменяем SimpleNamespace,
чтобы не зависеть от локального .env.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers import start as hstart
from keyboards.main import BTN_BACK

ADMIN_ID = 111111


@pytest.fixture(autouse=True)
def patched_cfg(monkeypatch, tmp_path):
    """Дефолтный конфиг: админ 111111, бэкап-канал не настроен."""
    monkeypatch.setattr(
        hstart,
        "_cfg",
        SimpleNamespace(
            admin_ids=frozenset({ADMIN_ID}),
            backup_chat_id=None,
            db_path=str(tmp_path / "test.db"),
        ),
    )


# ---------------------------------------------------------------------------
# /start, /help, /menu, /cancel
# ---------------------------------------------------------------------------


async def test_cmd_start_admin_gets_menu(test_db, make_message, fsm_state):
    await fsm_state.set_state("some:state")
    msg = make_message("/start")
    await hstart.cmd_start(msg, fsm_state)

    assert await fsm_state.get_state() is None
    assert "Добро пожаловать" in msg.answer.call_args[0][0]
    assert msg.answer.call_args.kwargs.get("reply_markup") is not None


async def test_cmd_start_unknown_user_denied(
    test_db, make_message, fsm_state
):
    """Новый пользователь не из ADMIN_IDS получает роль none и отказ."""
    msg = make_message("/start")
    msg.from_user.id = 555555
    await hstart.cmd_start(msg, fsm_state)

    assert "нет доступа" in msg.answer.call_args[0][0].lower()


async def test_cmd_help_resets_state(test_db, make_message, fsm_state):
    await fsm_state.set_state("some:state")
    msg = make_message("/help")
    await hstart.cmd_help(msg, fsm_state)

    assert await fsm_state.get_state() is None
    assert "Как пользоваться ботом" in msg.answer.call_args[0][0]


async def test_cmd_menu_full(test_db, make_message, fsm_state):
    msg = make_message("/menu")
    await hstart.cmd_menu(msg, fsm_state, role="full")

    assert "Главное меню" in msg.answer.call_args[0][0]


async def test_cmd_menu_none_denied(test_db, make_message, fsm_state):
    msg = make_message("/menu")
    await hstart.cmd_menu(msg, fsm_state, role="none")

    assert "нет доступа" in msg.answer.call_args[0][0].lower()


async def test_cmd_cancel(test_db, make_message, fsm_state):
    await fsm_state.set_state("some:state")
    msg = make_message("/cancel")
    await hstart.cmd_cancel(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert "отменено" in msg.answer.call_args[0][0].lower()


# ---------------------------------------------------------------------------
# /report
# ---------------------------------------------------------------------------


async def test_cmd_report_denied_for_non_full(test_db, make_message):
    msg = make_message("/report")
    await hstart.cmd_report(msg, role="operator")

    assert "нет доступа" in msg.answer.call_args[0][0].lower()


async def test_cmd_report_no_group_ids(test_db, make_message):
    msg = make_message("/report")  # conftest: bot._group_ids пуст
    await hstart.cmd_report(msg, role="full")

    assert "GROUP_IDS" in msg.answer.call_args[0][0]


async def test_cmd_report_shows_inline_menu(test_db, make_message):
    msg = make_message("/report")
    msg.bot._group_ids = frozenset({-1001})
    await hstart.cmd_report(msg, role="full")

    assert "Какой отчёт" in msg.answer.call_args[0][0]
    kb = msg.answer.call_args.kwargs["reply_markup"]
    callbacks = [
        b.callback_data for row in kb.inline_keyboard for b in row
    ]
    assert callbacks == [
        "cmd_report:morning", "cmd_report:evening", "cmd_report:xlsx"
    ]


# ---------------------------------------------------------------------------
# /backup
# ---------------------------------------------------------------------------


async def test_cmd_backup_denied_for_non_full(test_db, make_message):
    msg = make_message("/backup")
    await hstart.cmd_backup(msg, role="reports_only")

    assert "нет доступа" in msg.answer.call_args[0][0].lower()


async def test_cmd_backup_no_chat_id(test_db, make_message):
    msg = make_message("/backup")
    await hstart.cmd_backup(msg, role="full")

    assert "BACKUP_CHAT_ID" in msg.answer.call_args[0][0]


async def test_cmd_backup_sends(test_db, make_message, monkeypatch):
    monkeypatch.setattr(
        hstart,
        "_cfg",
        SimpleNamespace(
            admin_ids=frozenset({ADMIN_ID}),
            backup_chat_id=-1002,
            db_path=test_db,
        ),
    )
    msg = make_message("/backup")
    with patch(
        "services.scheduler._backup_db", new_callable=AsyncMock
    ) as backup_mock:
        await hstart.cmd_backup(msg, role="full")

    backup_mock.assert_awaited_once_with(msg.bot, -1002, test_db)
    assert "Бэкап отправлен" in msg.answer.call_args[0][0]


# ---------------------------------------------------------------------------
# Fallback-роутер
# ---------------------------------------------------------------------------


async def test_fallback_back_full(test_db, make_message, fsm_state):
    await fsm_state.set_state("some:state")
    msg = make_message(BTN_BACK)
    await hstart.fallback_back(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert "Главное меню" in msg.answer.call_args[0][0]


async def test_fallback_back_none_denied(test_db, make_message, fsm_state):
    msg = make_message(BTN_BACK)
    await hstart.fallback_back(msg, fsm_state, role="none")

    assert "нет доступа" in msg.answer.call_args[0][0].lower()


async def test_stale_callback_answered(test_db):
    callback = MagicMock()
    callback.from_user.id = ADMIN_ID
    callback.data = "old:button"
    callback.answer = AsyncMock()
    await hstart.stale_callback(callback)

    callback.answer.assert_awaited_once()
    assert "устарела" in callback.answer.call_args[0][0].lower()


async def test_stale_callback_from_channel(test_db):
    """Callback без from_user (пост канала) не падает."""
    callback = MagicMock()
    callback.from_user = None
    callback.data = "x"
    callback.answer = AsyncMock()
    await hstart.stale_callback(callback)

    callback.answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# Глобальный error handler
# ---------------------------------------------------------------------------


def _error_event(message=None, callback_query=None) -> MagicMock:
    event = MagicMock()
    event.exception = RuntimeError("boom")
    event.update.message = message
    event.update.callback_query = callback_query
    return event


async def test_error_handler_replies_to_message():
    message = MagicMock()
    message.answer = AsyncMock()
    await hstart.global_error_handler(_error_event(message=message))

    message.answer.assert_awaited_once()
    assert "ошибка" in message.answer.call_args[0][0].lower()


async def test_error_handler_replies_to_callback():
    callback = MagicMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    await hstart.global_error_handler(_error_event(callback_query=callback))

    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()


async def test_error_handler_no_targets():
    """Апдейт без message и callback (например, edited_message) — тишина."""
    await hstart.global_error_handler(_error_event())


async def test_error_handler_notify_fails_logged():
    """Ошибка при отправке уведомления не пробрасывается наружу."""
    message = MagicMock()
    message.answer = AsyncMock(side_effect=RuntimeError("network down"))
    await hstart.global_error_handler(_error_event(message=message))
