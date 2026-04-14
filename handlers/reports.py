"""Хэндлеры раздела отчётов — reply-first.

Поток: выбор типа отчёта (🟢 / 📋 / 🔴) → выбор режима (по всем / по
одной компании) → (опционально) выбор компании → генерация файла.

Один универсальный генератор (``services.report_generator.build_report``)
обслуживает все шесть комбинаций. Хэндлеры только собирают список
контейнеров и параметры (group_field, имя файла, подпись) и вызывают его.
"""
import asyncio
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from re import sub as re_sub

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from db import companies as db_comp
from db import containers as db_cont
from db.settings import get_all_settings
from keyboards.main import BTN_BACK, BTN_REPORTS, main_menu
from keyboards.reports import (
    BTN_REP_ACTIVE,
    BTN_REP_DEPARTED,
    BTN_REP_MIXED,
    BTN_SCOPE_ALL,
    BTN_SCOPE_COMPANY,
    report_company_select_reply_kb,
    reports_scope_reply_kb,
    reports_type_reply_kb,
)
from services.report_generator import build_report
from states import ReportsMenu

logger = logging.getLogger(__name__)
router = Router()

_REPORT_DIR = Path(tempfile.gettempdir()) / "container_reports"

# Внутренние коды типов отчётов (хранятся в FSM).
_TYPE_ACTIVE = "active"
_TYPE_MIXED = "mixed"
_TYPE_DEPARTED = "departed"

# Карта BTN → код типа. Двусторонняя навигация: текст кнопки ↔ код.
_BTN_TO_TYPE: dict[str, str] = {
    BTN_REP_ACTIVE: _TYPE_ACTIVE,
    BTN_REP_MIXED: _TYPE_MIXED,
    BTN_REP_DEPARTED: _TYPE_DEPARTED,
}

# Параметры генерации на каждый тип отчёта:
#   statuses     — какие статусы включать в выборку;
#   group_field  — поле, по которому берётся месяц листа;
#   filename     — шаблон имени файла (форматируется ниже);
#   caption_all  — подпись к файлу в режиме «по всем»;
#   caption_one  — подпись к файлу в режиме «по компании»
#                  (форматируется с подстановкой имени компании).
_REPORT_SPECS: dict[str, dict[str, object]] = {
    _TYPE_ACTIVE: {
        "statuses": ("on_terminal",),
        "group_field": "arrival_date",
        "summary_sheet": "Все активные",
        "file_prefix_all": "active_all",
        "file_prefix_company": "active",
        "caption_all": "✅ Отчёт по активным контейнерам готов!",
        "caption_one": "✅ Отчёт по активным контейнерам компании «{name}» готов!",
    },
    _TYPE_MIXED: {
        "statuses": ("on_terminal", "departed"),
        "group_field": "arrival_date",
        "summary_sheet": None,
        "file_prefix_all": "mixed_all",
        "file_prefix_company": "mixed",
        "caption_all": "✅ Отчёт по активным и вывезенным контейнерам готов!",
        "caption_one": (
            "✅ Отчёт по активным и вывезенным контейнерам компании "
            "«{name}» готов!"
        ),
    },
    _TYPE_DEPARTED: {
        "statuses": ("departed",),
        "group_field": "departure_date",
        "summary_sheet": None,
        "file_prefix_all": "departed_all",
        "file_prefix_company": "departed",
        "caption_all": "✅ Отчёт по вывезенным контейнерам готов!",
        "caption_one": "✅ Отчёт по вывезенным контейнерам компании «{name}» готов!",
    },
}


def _slugify(name: str) -> str:
    """Имя компании → безопасный для файловой системы идентификатор.

    Всё, что не буква/цифра/дефис, заменяется на '_' (включая нижнее
    подчёркивание — поэтому \\w не подходит и делаем явный класс).
    """
    cleaned = re_sub(r"[^A-Za-zА-Яа-я0-9\-]+", "_", name).strip("_")
    return cleaned or "company"


def _build_filename(
    spec: dict[str, object], company_name: str | None
) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if company_name is None:
        return f"{spec['file_prefix_all']}_{ts}.xlsx"
    safe = _slugify(company_name)
    return f"{spec['file_prefix_company']}_{safe}_{ts}.xlsx"


async def _reset_to_menu(message: Message, state: FSMContext) -> None:
    """Сброс FSM и возврат в меню типов отчётов."""
    await state.set_state(ReportsMenu.choosing_type)
    await state.update_data(report_type=None)
    await message.answer(
        "📊 <b>Раздел отчётов</b>\n\nВыберите тип отчёта:",
        reply_markup=reports_type_reply_kb(),
    )


async def _generate_and_send(
    message: Message,
    state: FSMContext,
    report_type: str,
    company: dict | None,
) -> None:
    """Собирает данные, вызывает генератор, отправляет файл, чистит FSM."""
    spec = _REPORT_SPECS[report_type]

    company_id = company["id"] if company is not None else None
    company_name = company["name"] if company is not None else None

    if company_name:
        await message.answer(f"⏳ Генерирую отчёт по «{company_name}»…")
    else:
        await message.answer("⏳ Генерирую отчёт…")

    containers = await db_cont.fetch_for_report(
        statuses=spec["statuses"],  # type: ignore[arg-type]
        company_id=company_id,
    )
    settings = await get_all_settings()

    filename = _build_filename(spec, company_name)
    # openpyxl-генерация синхронная и тяжёлая — без to_thread блокирует event
    # loop на секунды, и весь бот зависает для всех пользователей.
    path = await asyncio.to_thread(
        build_report,
        list(containers),
        settings,
        _REPORT_DIR,
        filename,
        group_field=spec["group_field"],  # type: ignore[arg-type]
        summary_sheet_name=spec["summary_sheet"],  # type: ignore[arg-type]
    )

    caption = (
        spec["caption_one"].format(name=company_name)  # type: ignore[union-attr]
        if company_name is not None
        else spec["caption_all"]
    )

    try:
        await message.answer_document(
            FSInputFile(path, filename=path.name),
            caption=caption,
        )
    finally:
        path.unlink(missing_ok=True)

    logger.info(
        "Отчёт отправлен: type=%s company_id=%s user=%s",
        report_type, company_id, message.from_user.id,
    )

    await _reset_to_menu(message, state)


# ---------------------------------------------------------------------------
# Вход в раздел
# ---------------------------------------------------------------------------


@router.message(F.text == BTN_REPORTS)
async def reports_menu(message: Message, state: FSMContext, role: str) -> None:
    if role not in ("full", "reports_only"):
        await message.answer("⛔ У вас нет доступа. Обратитесь к администратору.")
        return
    await _reset_to_menu(message, state)


# ---------------------------------------------------------------------------
# Состояние: выбор типа отчёта
# ---------------------------------------------------------------------------


@router.message(ReportsMenu.choosing_type, F.text == BTN_BACK)
async def type_back_to_main(
    message: Message, state: FSMContext, role: str
) -> None:
    await state.clear()
    await message.answer("Главное меню", reply_markup=main_menu(role))


@router.message(ReportsMenu.choosing_type, F.text.in_(tuple(_BTN_TO_TYPE)))
async def type_selected(message: Message, state: FSMContext) -> None:
    report_type = _BTN_TO_TYPE[message.text]
    await state.update_data(report_type=report_type)
    await state.set_state(ReportsMenu.choosing_scope)
    await message.answer(
        "Выберите режим:",
        reply_markup=reports_scope_reply_kb(),
    )


# ---------------------------------------------------------------------------
# Состояние: выбор режима (по всем / по одной компании)
# ---------------------------------------------------------------------------


@router.message(ReportsMenu.choosing_scope, F.text == BTN_BACK)
async def scope_back_to_type(message: Message, state: FSMContext) -> None:
    await _reset_to_menu(message, state)


@router.message(ReportsMenu.choosing_scope, F.text == BTN_SCOPE_ALL)
async def scope_all(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    report_type = data.get("report_type")
    if report_type not in _REPORT_SPECS:
        await _reset_to_menu(message, state)
        return
    await _generate_and_send(message, state, report_type, company=None)


@router.message(ReportsMenu.choosing_scope, F.text == BTN_SCOPE_COMPANY)
async def scope_company(message: Message, state: FSMContext) -> None:
    companies = await db_comp.list_companies()
    if not companies:
        await message.answer("⚠️ Нет компаний.")
        return
    await state.set_state(ReportsMenu.choosing_company)
    await message.answer(
        "🏢 Выберите компанию для отчёта:",
        reply_markup=report_company_select_reply_kb(companies),
    )


# ---------------------------------------------------------------------------
# Состояние: выбор компании
# ---------------------------------------------------------------------------


@router.message(ReportsMenu.choosing_company, F.text == BTN_BACK)
async def company_back_to_scope(message: Message, state: FSMContext) -> None:
    await state.set_state(ReportsMenu.choosing_scope)
    await message.answer(
        "Выберите режим:",
        reply_markup=reports_scope_reply_kb(),
    )


@router.message(ReportsMenu.choosing_company)
async def company_selected(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.startswith("🏢 "):
        return
    name = text[2:].strip()

    company = await db_comp.get_company_by_name_ci(name)
    if not company:
        await message.answer("⚠️ Компания не найдена, выберите из списка.")
        return

    data = await state.get_data()
    report_type = data.get("report_type")
    if report_type not in _REPORT_SPECS:
        await _reset_to_menu(message, state)
        return

    await _generate_and_send(
        message, state, report_type, company=dict(company)
    )
