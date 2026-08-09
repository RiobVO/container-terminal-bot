"""Тесты handlers/reports.py: тип отчёта → режим → компания → xlsx/csv."""
import codecs
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

from db import companies as db_comp
from db import containers as db_cont
from handlers import reports as h_reports
from keyboards.main import BTN_BACK
from keyboards.reports import (
    BTN_REP_ACTIVE,
    BTN_REP_DEPARTED,
    BTN_REP_MIXED,
    BTN_SCOPE_ALL,
    BTN_SCOPE_ALL_CSV,
    BTN_SCOPE_COMPANY,
    BTN_SCOPE_COMPANY_CSV,
)
from states import ReportsMenu


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d %H:%M:%S")


async def _seed_company() -> int:
    """Компания с одним активным и одним вывезенным контейнером."""
    company_id = await db_comp.add_company(name="Acme")
    await db_cont.add_container(
        number="CASS1234567",
        display_number="CASS 1234567",
        company_id=company_id,
        status="on_terminal",
        arrival_date=_days_ago(10),
        container_type="40HQ",
    )
    departed_id = await db_cont.add_container(
        number="TEMU7654321",
        display_number="TEMU 7654321",
        company_id=company_id,
        status="on_terminal",
        arrival_date=_days_ago(40),
    )
    await db_cont.set_departed(departed_id, _days_ago(5))
    return company_id


# ---------------------------------------------------------------------------
# Чистые функции
# ---------------------------------------------------------------------------


def test_slugify_keeps_letters_digits_dash():
    assert h_reports._slugify("Acme-2 Логистика") == "Acme-2_Логистика"


def test_slugify_only_symbols_falls_back():
    assert h_reports._slugify("!!! ???") == "company"


def test_build_filename_all_companies():
    spec = h_reports._REPORT_SPECS[h_reports._TYPE_ACTIVE]
    name = h_reports._build_filename(spec, None)
    assert name.startswith("active_all_")
    assert name.endswith(".xlsx")


def test_build_filename_single_company():
    spec = h_reports._REPORT_SPECS[h_reports._TYPE_DEPARTED]
    name = h_reports._build_filename(spec, "ООО Ромашка")
    assert name.startswith("departed_ООО_Ромашка_")
    assert name.endswith(".xlsx")


def test_build_filename_csv_extension():
    spec = h_reports._REPORT_SPECS[h_reports._TYPE_ACTIVE]
    assert h_reports._build_filename(spec, None, ext="csv").endswith(".csv")
    assert h_reports._build_filename(spec, "Acme", ext="csv").endswith(".csv")


# ---------------------------------------------------------------------------
# Вход в раздел
# ---------------------------------------------------------------------------


async def test_reports_menu_denied_for_other_roles(
    test_db, make_message, fsm_state
):
    for role in ("operator", "none"):
        msg = make_message(h_reports.BTN_REPORTS)
        await h_reports.reports_menu(msg, fsm_state, role=role)
        assert "нет доступа" in msg.answer.call_args[0][0].lower()
    assert await fsm_state.get_state() is None


async def test_reports_menu_opens_type_menu(test_db, make_message, fsm_state):
    msg = make_message(h_reports.BTN_REPORTS)
    await h_reports.reports_menu(msg, fsm_state, role="reports_only")

    assert await fsm_state.get_state() == ReportsMenu.choosing_type.state
    assert "Раздел отчётов" in msg.answer.call_args[0][0]


# ---------------------------------------------------------------------------
# Выбор типа отчёта
# ---------------------------------------------------------------------------


async def test_type_back_to_main_clears_state(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(ReportsMenu.choosing_type)
    msg = make_message(BTN_BACK)
    await h_reports.type_back_to_main(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert "Главное меню" in msg.answer.call_args[0][0]


async def test_type_selected_stores_type(test_db, make_message, fsm_state):
    for btn, expected in (
        (BTN_REP_ACTIVE, "active"),
        (BTN_REP_MIXED, "mixed"),
        (BTN_REP_DEPARTED, "departed"),
    ):
        await fsm_state.set_state(ReportsMenu.choosing_type)
        msg = make_message(btn)
        await h_reports.type_selected(msg, fsm_state)

        assert await fsm_state.get_state() == ReportsMenu.choosing_scope.state
        assert (await fsm_state.get_data())["report_type"] == expected


# ---------------------------------------------------------------------------
# Выбор режима
# ---------------------------------------------------------------------------


async def test_scope_back_returns_to_type_menu(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(ReportsMenu.choosing_scope)
    msg = make_message(BTN_BACK)
    await h_reports.scope_back_to_type(msg, fsm_state)

    assert await fsm_state.get_state() == ReportsMenu.choosing_type.state


async def test_scope_all_stale_type_resets(test_db, make_message, fsm_state):
    """report_type потерян (пережил деплой) — мягкий возврат в меню типов."""
    await fsm_state.set_state(ReportsMenu.choosing_scope)
    msg = make_message(BTN_SCOPE_ALL)
    msg.answer_document = AsyncMock()
    await h_reports.scope_all(msg, fsm_state)

    assert await fsm_state.get_state() == ReportsMenu.choosing_type.state
    msg.answer_document.assert_not_called()


async def test_scope_all_generates_and_sends(
    test_db, make_message, fsm_state
):
    await _seed_company()
    await fsm_state.set_state(ReportsMenu.choosing_scope)
    await fsm_state.update_data(report_type="mixed")
    msg = make_message(BTN_SCOPE_ALL)
    msg.answer_document = AsyncMock()
    await h_reports.scope_all(msg, fsm_state)

    doc = msg.answer_document.call_args
    assert "вывезенным контейнерам готов" in doc.kwargs["caption"]
    # Временный файл удалён после отправки
    assert not Path(doc.args[0].path).exists()
    # FSM сброшен в меню типов
    assert await fsm_state.get_state() == ReportsMenu.choosing_type.state
    assert (await fsm_state.get_data())["report_type"] is None


async def test_scope_all_csv_generates_and_sends(
    test_db, make_message, fsm_state
):
    """Кнопка CSV отдаёт документом настоящий CSV (BOM, «;») и удаляет файл."""
    await _seed_company()
    await fsm_state.set_state(ReportsMenu.choosing_scope)
    await fsm_state.update_data(report_type="mixed")
    msg = make_message(BTN_SCOPE_ALL_CSV)

    snapshot = {}

    async def _capture(doc, **kwargs):
        # Файл удаляется после отправки — содержимое снимаем в момент send
        snapshot["bytes"] = Path(doc.path).read_bytes()

    msg.answer_document = AsyncMock(side_effect=_capture)
    await h_reports.scope_all(msg, fsm_state)

    doc = msg.answer_document.call_args
    assert doc.args[0].filename.startswith("mixed_all_")
    assert doc.args[0].filename.endswith(".csv")
    assert snapshot["bytes"].startswith(codecs.BOM_UTF8)
    header = snapshot["bytes"].decode("utf-8-sig").splitlines()[0]
    assert header.startswith("Номер контейнера;Компания;")
    assert not Path(doc.args[0].path).exists()
    assert await fsm_state.get_state() == ReportsMenu.choosing_type.state


async def test_scope_company_csv_stores_format(
    test_db, make_message, fsm_state
):
    """Кнопка «CSV по компании» запоминает формат в FSM до выбора компании."""
    await _seed_company()
    await fsm_state.set_state(ReportsMenu.choosing_scope)
    msg = make_message(BTN_SCOPE_COMPANY_CSV)
    await h_reports.scope_company(msg, fsm_state)

    assert await fsm_state.get_state() == ReportsMenu.choosing_company.state
    assert (await fsm_state.get_data())["export_format"] == "csv"


async def test_scope_company_xlsx_overwrites_stale_csv_format(
    test_db, make_message, fsm_state
):
    """Обычная кнопка сбрасывает формат на xlsx — csv не «залипает»."""
    await _seed_company()
    await fsm_state.set_state(ReportsMenu.choosing_scope)
    await fsm_state.update_data(export_format="csv")
    msg = make_message(BTN_SCOPE_COMPANY)
    await h_reports.scope_company(msg, fsm_state)

    assert (await fsm_state.get_data())["export_format"] == "xlsx"


async def test_scope_company_without_companies(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(ReportsMenu.choosing_scope)
    msg = make_message(BTN_SCOPE_COMPANY)
    await h_reports.scope_company(msg, fsm_state)

    assert "Нет компаний" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() == ReportsMenu.choosing_scope.state


async def test_scope_company_shows_list(test_db, make_message, fsm_state):
    await _seed_company()
    await fsm_state.set_state(ReportsMenu.choosing_scope)
    msg = make_message(BTN_SCOPE_COMPANY)
    await h_reports.scope_company(msg, fsm_state)

    assert await fsm_state.get_state() == ReportsMenu.choosing_company.state
    assert "Выберите компанию" in msg.answer.call_args[0][0]


# ---------------------------------------------------------------------------
# Выбор компании
# ---------------------------------------------------------------------------


async def test_company_back_returns_to_scope(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(ReportsMenu.choosing_company)
    msg = make_message(BTN_BACK)
    await h_reports.company_back_to_scope(msg, fsm_state)

    assert await fsm_state.get_state() == ReportsMenu.choosing_scope.state


async def test_company_selected_ignores_foreign_text(
    test_db, make_message, fsm_state
):
    """Текст без префикса 🏢 не обрабатывается (фолбэк-роутер)."""
    await fsm_state.set_state(ReportsMenu.choosing_company)
    msg = make_message("произвольный текст")
    await h_reports.company_selected(msg, fsm_state)

    msg.answer.assert_not_called()
    assert await fsm_state.get_state() == ReportsMenu.choosing_company.state


async def test_company_selected_unknown_company(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(ReportsMenu.choosing_company)
    msg = make_message("🏢 Несуществующая")
    await h_reports.company_selected(msg, fsm_state)

    assert "не найдена" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() == ReportsMenu.choosing_company.state


async def test_company_selected_stale_type_resets(
    test_db, make_message, fsm_state
):
    await _seed_company()
    await fsm_state.set_state(ReportsMenu.choosing_company)
    msg = make_message("🏢 Acme")
    msg.answer_document = AsyncMock()
    await h_reports.company_selected(msg, fsm_state)

    assert await fsm_state.get_state() == ReportsMenu.choosing_type.state
    msg.answer_document.assert_not_called()


async def test_company_selected_generates_report(
    test_db, make_message, fsm_state
):
    await _seed_company()
    await fsm_state.set_state(ReportsMenu.choosing_company)
    await fsm_state.update_data(report_type="active")
    msg = make_message("🏢 Acme")
    msg.answer_document = AsyncMock()
    await h_reports.company_selected(msg, fsm_state)

    doc = msg.answer_document.call_args
    assert "Acme" in doc.kwargs["caption"]
    assert not Path(doc.args[0].path).exists()
    assert await fsm_state.get_state() == ReportsMenu.choosing_type.state


async def test_company_selected_departed_report(
    test_db, make_message, fsm_state
):
    """Отчёт по вывезенным группируется по departure_date — не падает."""
    await _seed_company()
    await fsm_state.set_state(ReportsMenu.choosing_company)
    await fsm_state.update_data(report_type="departed")
    msg = make_message("🏢 Acme")
    msg.answer_document = AsyncMock()
    await h_reports.company_selected(msg, fsm_state)

    doc = msg.answer_document.call_args
    assert "вывезенным" in doc.kwargs["caption"]
    assert doc.args[0].filename.startswith("departed_Acme_")


async def test_company_selected_csv_report(
    test_db, make_message, fsm_state
):
    """Формат csv из FSM доезжает до файла при выборе компании."""
    await _seed_company()
    await fsm_state.set_state(ReportsMenu.choosing_company)
    await fsm_state.update_data(report_type="active", export_format="csv")
    msg = make_message("🏢 Acme")
    msg.answer_document = AsyncMock()
    await h_reports.company_selected(msg, fsm_state)

    doc = msg.answer_document.call_args
    assert doc.args[0].filename.startswith("active_Acme_")
    assert doc.args[0].filename.endswith(".csv")
    assert "Acme" in doc.kwargs["caption"]
    assert not Path(doc.args[0].path).exists()
    assert await fsm_state.get_state() == ReportsMenu.choosing_type.state
