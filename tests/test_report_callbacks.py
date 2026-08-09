"""Тесты handlers/report_callbacks.py: inline-кнопки утреннего отчёта и /report."""
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery

from db import companies as db_comp
from db import containers as db_cont
from handlers import report_callbacks as h_cb


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
def make_callback():
    """Фабрика mock-колбэков для прямого вызова callback-хендлеров."""

    def _make(data: str = "") -> MagicMock:
        cb = MagicMock(spec=CallbackQuery)
        cb.data = data
        cb.answer = AsyncMock()
        msg = MagicMock()
        msg.answer = AsyncMock()
        msg.answer_document = AsyncMock()
        cb.message = msg
        bot = MagicMock()
        bot._group_ids = frozenset()
        bot.send_document = AsyncMock()
        cb.bot = bot
        return cb

    return _make


async def _seed(
    *,
    days_ago: int,
    number: str,
    company_id: int,
    status: str = "on_terminal",
) -> int:
    return await db_cont.add_container(
        number=number,
        display_number=f"{number[:4]} {number[4:]}",
        company_id=company_id,
        status=status,
        arrival_date=_days_ago(days_ago),
    )


# ---------------------------------------------------------------------------
# morning:companies
# ---------------------------------------------------------------------------


async def test_morning_companies_empty(test_db, make_callback):
    cb = make_callback("morning:companies")
    await h_cb.morning_companies(cb)

    cb.answer.assert_awaited_once_with(
        "Нет контейнеров на терминале", show_alert=True
    )
    cb.message.answer.assert_not_called()


async def test_morning_companies_breakdown(test_db, make_callback):
    """Два контейнера одной компании суммируются, departed не считается."""
    acme = await db_comp.add_company(name="Acme")
    beta = await db_comp.add_company(name="Beta")
    await _seed(days_ago=10, number="CASS1234567", company_id=acme)
    await _seed(days_ago=5, number="CASS7654321", company_id=acme)
    await _seed(days_ago=3, number="TEMU1111111", company_id=beta)
    departed = await _seed(days_ago=40, number="TEMU2222222", company_id=beta)
    await db_cont.set_departed(departed)

    cb = make_callback("morning:companies")
    await h_cb.morning_companies(cb)

    text = cb.message.answer.call_args[0][0]
    assert "По компаниям" in text
    assert "🏢 Acme: 2 шт" in text
    assert "🏢 Beta: 1 шт" in text
    cb.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# morning:warnings
# ---------------------------------------------------------------------------


async def test_morning_warnings_none(test_db, make_callback):
    """Свежий контейнер (запас > 7 дней) и in_transit не дают предупреждений."""
    acme = await db_comp.add_company(name="Acme")
    await _seed(days_ago=10, number="CASS1234567", company_id=acme)
    await db_cont.add_container(
        number="TEMU1111111",
        display_number="TEMU 1111111",
        company_id=acme,
        status="in_transit",
        arrival_date=None,
    )

    cb = make_callback("morning:warnings")
    await h_cb.morning_warnings(cb)

    cb.answer.assert_awaited_once_with("Нет предупреждений", show_alert=True)
    cb.message.answer.assert_not_called()


async def test_morning_warnings_levels(test_db, make_callback):
    """Красный/жёлтый/зелёный уровни + контейнер без компании (—)."""
    acme = await db_comp.add_company(name="Acme")
    # free_days=30 (дефолт из test_db): 40 дн → red, 28 → yellow, 25 → green
    await _seed(days_ago=40, number="CASS1234567", company_id=acme)
    await _seed(days_ago=28, number="CASS7654321", company_id=acme)
    # company_id без записи в companies → company_name NULL → «—»
    await _seed(days_ago=25, number="TEMU1111111", company_id=999999)

    cb = make_callback("morning:warnings")
    await h_cb.morning_warnings(cb)

    text = cb.message.answer.call_args[0][0]
    assert "Все предупреждения" in text
    assert "🔴 CASS 1234567 (Acme) — 10 дн. на тарификации" in text
    assert "🟡 CASS 7654321 (Acme) — через 2 дн." in text
    assert "💚 TEMU 1111111 (—) — через 5 дн." in text
    # Сортировка: красный (отрицательный остаток) первым
    assert text.index("🔴") < text.index("🟡") < text.index("💚")
    cb.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# morning:xlsx
# ---------------------------------------------------------------------------


async def test_morning_xlsx_empty(test_db, make_callback):
    cb = make_callback("morning:xlsx")
    await h_cb.morning_xlsx(cb)

    cb.answer.assert_awaited_once_with("Нет данных для отчёта", show_alert=True)
    cb.message.answer_document.assert_not_called()


async def test_morning_xlsx_sends_document(test_db, make_callback):
    acme = await db_comp.add_company(name="Acme")
    await _seed(days_ago=10, number="CASS1234567", company_id=acme)

    cb = make_callback("morning:xlsx")
    await h_cb.morning_xlsx(cb)

    doc = cb.message.answer_document.call_args
    assert doc.kwargs["caption"] == "📊 Отчёт по всем контейнерам"
    assert not Path(doc.args[0].path).exists()  # файл удалён после отправки
    cb.answer.assert_awaited_once_with()


async def test_morning_xlsx_unlink_error_swallowed(
    test_db, make_callback, monkeypatch, tmp_path
):
    """Несуществующий файл при unlink не роняет хендлер (except OSError)."""
    acme = await db_comp.add_company(name="Acme")
    await _seed(days_ago=10, number="CASS1234567", company_id=acme)
    fake_path = tmp_path / "missing.xlsx"
    monkeypatch.setattr(
        h_cb, "build_report", lambda *a, **kw: fake_path
    )

    cb = make_callback("morning:xlsx")
    await h_cb.morning_xlsx(cb)

    cb.message.answer_document.assert_awaited_once()
    cb.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# cmd_report:morning / cmd_report:evening
# ---------------------------------------------------------------------------


async def test_cmd_report_morning_no_groups(test_db, make_callback):
    cb = make_callback("cmd_report:morning")
    await h_cb.cmd_report_morning(cb)

    cb.answer.assert_awaited_once_with(
        "GROUP_IDS не настроены", show_alert=True
    )


async def test_cmd_report_morning_sends_to_groups(
    test_db, make_callback, monkeypatch
):
    build_mock = AsyncMock(return_value="утренний текст")
    notify_mock = AsyncMock()
    monkeypatch.setattr(h_cb, "build_morning_report", build_mock)
    monkeypatch.setattr(h_cb, "notify_groups", notify_mock)

    cb = make_callback("cmd_report:morning")
    cb.bot._group_ids = frozenset({-100})
    await h_cb.cmd_report_morning(cb)

    build_mock.assert_awaited_once()
    args = notify_mock.await_args
    assert args.args[1] == frozenset({-100})
    assert args.args[2] == "утренний текст"
    assert args.kwargs["reply_markup"] is not None
    cb.answer.assert_awaited_once_with(
        "✅ Утренний отчёт отправлен в канал", show_alert=True
    )


async def test_cmd_report_evening_no_groups(test_db, make_callback):
    cb = make_callback("cmd_report:evening")
    await h_cb.cmd_report_evening(cb)

    cb.answer.assert_awaited_once_with(
        "GROUP_IDS не настроены", show_alert=True
    )


async def test_cmd_report_evening_sends_to_groups(
    test_db, make_callback, monkeypatch
):
    build_mock = AsyncMock(return_value="вечерний текст")
    notify_mock = AsyncMock()
    monkeypatch.setattr(h_cb, "build_evening_report", build_mock)
    monkeypatch.setattr(h_cb, "notify_groups", notify_mock)

    cb = make_callback("cmd_report:evening")
    cb.bot._group_ids = frozenset({-100})
    await h_cb.cmd_report_evening(cb)

    build_mock.assert_awaited_once()
    assert notify_mock.await_args.args[2] == "вечерний текст"
    cb.answer.assert_awaited_once_with(
        "✅ Итоги дня отправлены в канал", show_alert=True
    )


# ---------------------------------------------------------------------------
# cmd_report:xlsx
# ---------------------------------------------------------------------------


async def test_cmd_report_xlsx_no_groups(test_db, make_callback):
    cb = make_callback("cmd_report:xlsx")
    await h_cb.cmd_report_xlsx(cb)

    cb.answer.assert_awaited_once_with(
        "GROUP_IDS не настроены", show_alert=True
    )


async def test_cmd_report_xlsx_no_data(test_db, make_callback):
    cb = make_callback("cmd_report:xlsx")
    cb.bot._group_ids = frozenset({-100})
    await h_cb.cmd_report_xlsx(cb)

    cb.answer.assert_awaited_once_with("Нет данных для отчёта", show_alert=True)
    cb.bot.send_document.assert_not_called()


async def test_cmd_report_xlsx_sends_with_partial_failure(
    test_db, make_callback
):
    """Ошибка отправки в одну группу не ломает отправку в другую."""
    acme = await db_comp.add_company(name="Acme")
    await _seed(days_ago=10, number="CASS1234567", company_id=acme)

    cb = make_callback("cmd_report:xlsx")
    cb.bot._group_ids = frozenset({-100, -200})
    cb.bot.send_document.side_effect = [Exception("fail"), None]
    await h_cb.cmd_report_xlsx(cb)

    assert cb.bot.send_document.await_count == 2
    cb.answer.assert_awaited_once_with(
        "✅ xlsx отправлен в канал", show_alert=True
    )


async def test_cmd_report_xlsx_unlink_error_swallowed(
    test_db, make_callback, monkeypatch, tmp_path
):
    """Несуществующий файл при unlink не роняет хендлер (except OSError)."""
    acme = await db_comp.add_company(name="Acme")
    await _seed(days_ago=10, number="CASS1234567", company_id=acme)
    fake_path = tmp_path / "missing.xlsx"
    monkeypatch.setattr(
        h_cb, "build_report", lambda *a, **kw: fake_path
    )

    cb = make_callback("cmd_report:xlsx")
    cb.bot._group_ids = frozenset({-100})
    await h_cb.cmd_report_xlsx(cb)

    cb.bot.send_document.assert_awaited_once()
    cb.answer.assert_awaited_once_with(
        "✅ xlsx отправлен в канал", show_alert=True
    )
