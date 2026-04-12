import logging
import tempfile
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from db import containers_by_month, get_company, get_company_by_name, get_user_role, list_companies
from keyboards import BTN_REPORT, cancel_reply_kb, companies_reply_kb, main_menu, months_kb, report_kind_kb
from reports import build_report
from utils import safe_delete

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")

# Временная директория для отчётов
_REPORT_DIR = Path(tempfile.gettempdir()) / "container_reports"


class ReportFlow(StatesGroup):
    company = State()
    month = State()
    kind = State()


# ---------------------------------------------------------------------------
# Вход
# ---------------------------------------------------------------------------


@router.message(F.text == BTN_REPORT)
async def start_report(message: Message, state: FSMContext) -> None:
    await safe_delete(message)
    companies = await list_companies()
    if not companies:
        await message.answer("⚠️ Нет ни одной компании. Сначала добавь компанию.")
        return
    await state.set_state(ReportFlow.company)
    await message.answer(
        "Выбери компанию для отчёта:",
        reply_markup=companies_reply_kb(companies),
    )


# ---------------------------------------------------------------------------
# Шаг 1: компания
# ---------------------------------------------------------------------------


@router.message(ReportFlow.company)
async def process_company(message: Message, state: FSMContext) -> None:
    await safe_delete(message)
    name = (message.text or "").strip()
    company = await get_company_by_name(name)
    if not company:
        await message.answer("❌ Компания не найдена. Выбери из списка.")
        return
    await state.update_data(company_id=company["id"])
    await state.set_state(ReportFlow.month)
    await message.answer(
        "Выбери месяц:",
        reply_markup=months_kb("rep_month"),
    )


# ---------------------------------------------------------------------------
# Шаг 2: месяц
# ---------------------------------------------------------------------------


@router.callback_query(ReportFlow.month, F.data.startswith("rep_month:"))
async def process_month(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    await safe_delete(callback.message)

    if value == "cancel":
        await state.clear()
        role = await get_user_role(callback.from_user.id)
        await callback.message.answer("Отменено.", reply_markup=main_menu(role == "admin"))
        await callback.answer()
        return

    await state.update_data(year_month=value)
    await state.set_state(ReportFlow.kind)
    await callback.message.answer(
        "Выбери вид отчёта:",
        reply_markup=report_kind_kb("rep_kind"),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 3: вид отчёта → генерация
# ---------------------------------------------------------------------------


@router.callback_query(ReportFlow.kind, F.data.startswith("rep_kind:"))
async def process_kind(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    await safe_delete(callback.message)

    if value == "cancel":
        await state.clear()
        role = await get_user_role(callback.from_user.id)
        await callback.message.answer("Отменено.", reply_markup=main_menu(role == "admin"))
        await callback.answer()
        return

    data = await state.get_data()
    await state.clear()

    company_id = data["company_id"]
    year_month = data["year_month"]
    departed_only = value == "departed"

    company = await get_company(company_id)
    containers = await containers_by_month(company_id, year_month, departed_only)

    if not containers:
        month_label = _fmt_month(year_month)
        await callback.message.answer(
            f"ℹ️ За {month_label} нет контейнеров"
            f"{' (вывезенных)' if departed_only else ''}."
        )
        await callback.answer()
        return

    await callback.answer("Генерирую отчёт…")

    path = build_report(company, containers, value, _REPORT_DIR)

    month_label = _fmt_month(year_month)
    if departed_only:
        caption = (
            f"✅ Отчёт по вывезенным контейнерам компании «{company['name']}» "
            f"за {month_label} готов!"
        )
    else:
        caption = f"✅ Отчёт по компании «{company['name']}» за {month_label} готов!"

    try:
        await callback.message.answer_document(
            FSInputFile(path, filename=path.name),
            caption=caption,
        )
    finally:
        path.unlink(missing_ok=True)

    logger.info(
        "Отчёт отправлен: company=%s month=%s kind=%s user=%s",
        company["name"], year_month, value, callback.from_user.id,
    )


def _fmt_month(year_month: str) -> str:
    """Форматирует 'YYYY-MM' → 'MM.YYYY' для отображения."""
    year, month = year_month.split("-")
    return f"{month}.{year}"
