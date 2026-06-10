"""Дополнительные тесты handlers/register.py: отмены, фолбэки,
ручной ввод даты, форматирование даты, уведомления в группы.

Happy-path покрыт в tests/test_register_flow.py — здесь только ветки,
не затронутые там.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from db import companies as db_comp
from db import containers as db_cont
from handlers import register
from states import RegisterContainer


def _base_data() -> dict:
    return {"number": "CASS1234567", "display_number": "CASS 1234567"}


async def _full_data() -> dict:
    company_id = await db_comp.add_company(name="Ромашка")
    return {
        **_base_data(),
        "company_id": company_id,
        "company_name": "Ромашка",
        "container_type": "40HQ",
    }


# ---------------------------------------------------------------------------
# Шаг компании: пустое название
# ---------------------------------------------------------------------------


async def test_process_company_empty_name(test_db, make_message, fsm_state):
    """Пробельный ввод не создаёт компанию и не двигает FSM."""
    await fsm_state.set_state(RegisterContainer.waiting_for_company)
    await fsm_state.set_data(_base_data())
    msg = make_message("   ")
    await register.process_company(msg, fsm_state, role="full")

    assert "Введите название компании" in msg.answer.call_args[0][0]
    assert await db_comp.list_companies() == []
    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_company.state
    )


# ---------------------------------------------------------------------------
# Шаг даты прибытия: отмена, ручной ввод, фолбэк
# ---------------------------------------------------------------------------


async def test_arrival_cancel(test_db, make_message, fsm_state):
    await fsm_state.set_state(RegisterContainer.waiting_for_arrival_date)
    await fsm_state.set_data(await _full_data())
    msg = make_message()
    await register.arrival_cancel(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert await db_cont.find_by_number("CASS1234567") is None


async def test_arrival_manual_prompt(test_db, make_message, fsm_state):
    await fsm_state.set_state(RegisterContainer.waiting_for_arrival_date)
    msg = make_message()
    await register.arrival_manual_prompt(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_manual_date.state
    )
    assert "ДД.ММ.ГГГГ" in msg.answer.call_args[0][0]


async def test_arrival_fallback(test_db, make_message):
    msg = make_message("произвольный текст")
    await register.arrival_fallback(msg)

    assert "из кнопок" in msg.answer.call_args[0][0]


async def test_manual_date_cancel(test_db, make_message, fsm_state):
    await fsm_state.set_state(RegisterContainer.waiting_for_manual_date)
    await fsm_state.set_data(await _full_data())
    msg = make_message()
    await register.manual_date_cancel(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert await db_cont.find_by_number("CASS1234567") is None


async def test_manual_date_invalid_format(test_db, make_message, fsm_state):
    await fsm_state.set_state(RegisterContainer.waiting_for_manual_date)
    await fsm_state.set_data(await _full_data())
    msg = make_message("2026-06-01")
    await register.manual_date_process(msg, fsm_state, role="full")

    assert "Неверный формат" in msg.answer.call_args[0][0]
    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_manual_date.state
    )
    assert await db_cont.find_by_number("CASS1234567") is None


async def test_manual_date_in_future_rejected(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(RegisterContainer.waiting_for_manual_date)
    await fsm_state.set_data(await _full_data())
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
    msg = make_message(tomorrow)
    await register.manual_date_process(msg, fsm_state, role="full")

    assert "не может быть в будущем" in msg.answer.call_args[0][0]
    assert await db_cont.find_by_number("CASS1234567") is None


# ---------------------------------------------------------------------------
# Шаг типа: отмена и фолбэк
# ---------------------------------------------------------------------------


async def test_type_cancel(test_db, make_message, fsm_state):
    await fsm_state.set_state(RegisterContainer.waiting_for_type)
    await fsm_state.set_data(await _full_data())
    msg = make_message()
    await register.type_cancel(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert await db_cont.find_by_number("CASS1234567") is None


async def test_type_fallback(test_db, make_message):
    msg = make_message("не тип")
    await register.type_fallback(msg)

    assert "Пропустить" in msg.answer.call_args[0][0]


# ---------------------------------------------------------------------------
# Форматирование даты прибытия для карточки
# ---------------------------------------------------------------------------


def test_fmt_arrival_display_none():
    assert register._fmt_arrival_display(None) == "—"
    assert register._fmt_arrival_display("") == "—"


def test_fmt_arrival_display_formats():
    # Полный формат и короткий (второй матчится после ValueError первого)
    assert (
        register._fmt_arrival_display("2026-06-01 10:30:00") == "01.06.2026"
    )
    assert register._fmt_arrival_display("2026-06-01") == "01.06.2026"


def test_fmt_arrival_display_unparseable_returned_as_is():
    assert register._fmt_arrival_display("вчера") == "вчера"


# ---------------------------------------------------------------------------
# Live-лента: уведомление в группы после регистрации
# ---------------------------------------------------------------------------


async def test_finalize_notifies_groups(test_db, make_message, fsm_state):
    """При непустых _group_ids после сохранения уходит уведомление."""
    await fsm_state.set_state(RegisterContainer.waiting_for_arrival_date)
    await fsm_state.set_data(await _full_data())
    msg = make_message()
    msg.bot._group_ids = frozenset({-1001})

    with patch(
        "services.group_notify.notify_groups", new_callable=AsyncMock
    ) as notify_mock:
        await register.arrival_today(msg, fsm_state, role="full")

    notify_mock.assert_awaited_once()
    bot_arg, gids_arg, text_arg = notify_mock.call_args[0]
    assert bot_arg is msg.bot
    assert gids_arg == frozenset({-1001})
    assert "CASS 1234567" in text_arg
    assert "На терминале" in text_arg
    assert "@operator" in text_arg
    assert await db_cont.find_by_number("CASS1234567") is not None


async def test_finalize_notify_transit_without_username(
    test_db, make_message, fsm_state
):
    """В пути + у оператора нет username — берётся full_name."""
    await fsm_state.set_state(RegisterContainer.waiting_for_arrival_date)
    await fsm_state.set_data(await _full_data())
    msg = make_message()
    msg.from_user.username = None
    msg.bot._group_ids = frozenset({-1001})

    with patch(
        "services.group_notify.notify_groups", new_callable=AsyncMock
    ) as notify_mock:
        await register.arrival_transit(msg, fsm_state, role="full")

    text_arg = notify_mock.call_args[0][2]
    assert "В пути" in text_arg
    assert "Operator" in text_arg
