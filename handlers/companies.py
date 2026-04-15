"""Хэндлеры раздела «Компании» — reply-first.

Гибкая модель тарифа: у компании четыре параметра (entry_fee, free_days,
storage_rate, storage_period_days), каждое NULL означает «стандартное из
global_settings».
"""
import logging
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from db import companies as db_comp
from db import containers as db_cont
from db.settings import get_all_settings
from keyboards.companies import (
    BTN_ADD_COMPANY,
    BTN_CANCEL_X,
    BTN_COMPANIES_BACK,
    BTN_COMPANY_DELETE,
    BTN_COMPANY_EDIT_ENTRY,
    BTN_COMPANY_EDIT_FREE_DAYS,
    BTN_COMPANY_EDIT_STORAGE_PERIOD,
    BTN_COMPANY_EDIT_STORAGE_RATE,
    BTN_COMPANY_RENAME,
    BTN_CONFIRM_DELETE,
    BTN_RESET_DEFAULT,
    companies_list_reply_kb,
    company_card_reply_kb,
    company_delete_confirm_reply_kb,
    company_edit_field_reply_kb,
    company_rename_reply_kb,
)
from keyboards.main import BTN_BACK, BTN_COMPANIES, main_menu
from services.calculator import calculate_container_cost
from services.telegram_utils import send_long
from states import (
    CompaniesSection,
    EditCompanyEntry,
    EditCompanyFreeDays,
    EditCompanyName,
    EditCompanyStoragePeriod,
    EditCompanyStorageRate,
)

logger = logging.getLogger(__name__)
router = Router()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_short_date(val: str | None) -> str:
    if not val:
        return "—"
    from datetime import datetime
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return val


def _parse_float(text: str | None) -> float | None:
    try:
        v = float((text or "").strip().replace(",", "."))
        return v if v >= 0 else None
    except ValueError:
        return None


def _parse_int_nonneg(text: str | None) -> int | None:
    try:
        v = int((text or "").strip())
        return v if v >= 0 else None
    except ValueError:
        return None


def _parse_int_positive(text: str | None) -> int | None:
    try:
        v = int((text or "").strip())
        return v if v >= 1 else None
    except ValueError:
        return None


def _mark(is_custom: bool) -> str:
    return "индивидуальный" if is_custom else "стандартный"


def _period_label(period_days: int) -> str:
    if period_days <= 1:
        return "ежедневный тариф"
    if period_days == 30:
        return "ежемесячный тариф"
    return f"каждые {period_days} дн."


async def _show_companies_list(message: Message, state: FSMContext) -> None:
    """Отправляет экран списка компаний.

    Счётчики активных контейнеров подтягиваются одним запросом с JOIN —
    без N+1. Результат отсортирован регистронезависимо самим SQL.
    """
    companies = await db_comp.list_companies_with_active_counts()

    await message.answer("🏢 Раздел компаний")

    if not companies:
        await message.answer("🏢 <b>Компании</b>\n\nКомпаний пока нет.")
        await state.set_state(CompaniesSection.list)
        await state.update_data(companies_map={})
        return

    kb, mapping = companies_list_reply_kb(companies)
    await message.answer(
        "🏢 <b>Компании</b>\n\nВыберите компанию:",
        reply_markup=kb,
    )
    await state.set_state(CompaniesSection.list)
    await state.update_data(companies_map=mapping)


async def _show_company_card(
    message: Message,
    state: FSMContext,
    company_id: int,
) -> None:
    """Отправляет карточку компании с гибкой моделью тарифа."""
    company = await db_comp.get_company(company_id)
    if not company:
        await message.answer("⚠️ Компания не найдена.")
        await _show_companies_list(message, state)
        return

    settings = await get_all_settings()
    default_entry = float(settings.get("default_entry_fee", 20.0))
    default_free = int(settings.get("default_free_days", 30))
    default_rate = float(settings.get("default_storage_rate", 20.0))
    default_period = int(settings.get("default_storage_period_days", 30))

    entry_fee = (
        company["entry_fee"]
        if company["entry_fee"] is not None
        else default_entry
    )
    free_days = (
        company["free_days"]
        if company["free_days"] is not None
        else default_free
    )
    storage_rate = (
        company["storage_rate"]
        if company["storage_rate"] is not None
        else default_rate
    )
    storage_period = (
        company["storage_period_days"]
        if company["storage_period_days"] is not None
        else default_period
    )

    entry_mark = _mark(company["entry_fee"] is not None)
    free_mark = _mark(company["free_days"] is not None)
    rate_mark = _mark(company["storage_rate"] is not None)
    period_mark = _mark(company["storage_period_days"] is not None)
    period_label = _period_label(int(storage_period))

    active_containers = await db_cont.active_for_company(company_id)
    total_ever = await db_comp.count_total_containers(company_id)
    active_count = len(active_containers)

    total_debt = 0.0
    # Калькулятору нужны status/arrival_date/departure_date — всё это уже
    # есть в строках active_for_company, лишний get_container на каждый
    # контейнер был N+1-запросом. Тариф берём из уже загруженной company.
    for c in active_containers:
        if c["status"] == "on_terminal":
            cost = calculate_container_cost(
                c,
                settings,
                comp_entry_fee=company["entry_fee"],
                comp_free_days=company["free_days"],
                comp_storage_rate=company["storage_rate"],
                comp_storage_period_days=company["storage_period_days"],
            )
            total_debt += cost["total"]

    active_lines = [
        f"📦 {c['display_number']} (с {_fmt_short_date(c['arrival_date'])})"
        for c in active_containers
    ]
    active_text = "\n".join(active_lines) if active_lines else "—"

    text = (
        f"🏢 <b>{escape(company['name'])}</b>\n\n"
        f"💰 Стоимость входа: {entry_fee} $ ({entry_mark})\n"
        f"🆓 Бесплатных дней: {free_days} ({free_mark})\n"
        f"💵 Платное хранение: {storage_rate} $ за {storage_period} дн. "
        f"({rate_mark})\n"
        f"📅 Период начисления: {period_label} ({period_mark})\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Занятых контейнеров: {active_count}\n"
        f"• Всего контейнеров за время: {total_ever}\n"
        f"💰 К оплате: {total_debt:.2f} $\n\n"
        f"<b>Активные контейнеры:</b>\n{active_text}"
    )

    kb = company_card_reply_kb()
    await state.set_state(CompaniesSection.card)
    await state.update_data(company_id=company_id)
    # Если у компании сотни активных контейнеров — текст вылезает за
    # Telegram-лимит 4096 символов и прежний message.answer падал с
    # TelegramBadRequest. send_long режет на чанки и шлёт по очереди.
    await send_long(message, text, reply_markup=kb)


# ---------------------------------------------------------------------------
# Вход в раздел
# ---------------------------------------------------------------------------


@router.message(F.text == BTN_COMPANIES)
async def companies_menu(
    message: Message, state: FSMContext, role: str
) -> None:
    if role != "full":
        await message.answer("⛔ У вас нет доступа. Обратитесь к администратору.")
        return
    await state.clear()
    await _show_companies_list(message, state)


# ---------------------------------------------------------------------------
# Состояние: список компаний
# ---------------------------------------------------------------------------


@router.message(CompaniesSection.list, F.text == BTN_BACK)
async def companies_back(
    message: Message, state: FSMContext, role: str
) -> None:
    await state.clear()
    await message.answer("Главное меню", reply_markup=main_menu(role))


@router.message(CompaniesSection.list, F.text == BTN_ADD_COMPANY)
async def companies_add_start(message: Message, state: FSMContext) -> None:
    """Начало добавления новой компании."""
    await state.set_state(CompaniesSection.adding_name)
    await message.answer(
        "➕ <b>Добавление новой компании</b>\n\n"
        "Введите название компании (1–64 символа).\n"
        "Тарифы можно будет настроить после создания.",
        reply_markup=company_rename_reply_kb(),
    )


@router.message(CompaniesSection.list)
async def companies_list_select(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    mapping: dict[str, int] = data.get("companies_map", {})
    if text not in mapping:
        return
    await _show_company_card(message, state, mapping[text])


# ---------------------------------------------------------------------------
# Состояние: добавление новой компании
# ---------------------------------------------------------------------------


@router.message(CompaniesSection.adding_name, F.text == BTN_CANCEL_X)
async def companies_add_cancel(message: Message, state: FSMContext) -> None:
    await _show_companies_list(message, state)


@router.message(CompaniesSection.adding_name)
async def companies_add_process(
    message: Message, state: FSMContext
) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        await message.answer("❌ Название должно быть от 1 до 64 символов.")
        return
    existing = await db_comp.get_company_by_name_ci(name)
    if existing:
        await message.answer(f"❌ Компания «{escape(name)}» уже существует.")
        return

    company_id = await db_comp.add_company(name=name)
    logger.info("Компания создана из списка: %s (id=%s)", name, company_id)
    await message.answer(f"✅ Компания «{escape(name)}» создана")
    await _show_company_card(message, state, company_id)


# ---------------------------------------------------------------------------
# Состояние: карточка компании
# ---------------------------------------------------------------------------


@router.message(CompaniesSection.card, F.text == BTN_COMPANIES_BACK)
async def card_back(message: Message, state: FSMContext) -> None:
    await _show_companies_list(message, state)


async def _begin_edit_field(
    message: Message,
    state: FSMContext,
    fsm_state,
    title: str,
    current_text: str,
    prompt: str,
) -> None:
    """Общий шаблон входа в редактор одного поля тарифа."""
    data = await state.get_data()
    company_id = data.get("company_id")
    if company_id is None:
        return
    company = await db_comp.get_company(company_id)
    if not company:
        return
    await state.set_state(fsm_state)
    await state.update_data(company_id=company_id)
    await message.answer(
        f'{title} компании "<b>{escape(company["name"])}</b>"\n\n'
        f"{current_text}\n\n"
        f"{prompt}",
        reply_markup=company_edit_field_reply_kb(),
    )


@router.message(CompaniesSection.card, F.text == BTN_COMPANY_EDIT_ENTRY)
async def card_edit_entry(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    company = await db_comp.get_company(data.get("company_id"))
    if not company:
        return
    settings = await get_all_settings()
    default_val = float(settings.get("default_entry_fee", 20.0))
    current = (
        company["entry_fee"]
        if company["entry_fee"] is not None
        else default_val
    )
    label = _mark(company["entry_fee"] is not None)
    await _begin_edit_field(
        message, state, EditCompanyEntry.waiting_for_value,
        title="💰 <b>Стоимость входа</b>",
        current_text=f"Текущая стоимость: {current} $ ({label})",
        prompt=(
            "Введите новую индивидуальную стоимость (число ≥ 0).\n"
            f"Или нажмите 🔄 Сбросить на стандартную ({default_val} $)."
        ),
    )


@router.message(CompaniesSection.card, F.text == BTN_COMPANY_EDIT_FREE_DAYS)
async def card_edit_free_days(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    company = await db_comp.get_company(data.get("company_id"))
    if not company:
        return
    settings = await get_all_settings()
    default_val = int(settings.get("default_free_days", 30))
    current = (
        company["free_days"]
        if company["free_days"] is not None
        else default_val
    )
    label = _mark(company["free_days"] is not None)
    await _begin_edit_field(
        message, state, EditCompanyFreeDays.waiting_for_value,
        title="🆓 <b>Бесплатные дни</b>",
        current_text=f"Текущее значение: {current} дн. ({label})",
        prompt=(
            "Введите новое количество бесплатных дней (целое число ≥ 0).\n"
            f"Или нажмите 🔄 Сбросить на стандартную ({default_val} дн.)."
        ),
    )


@router.message(CompaniesSection.card, F.text == BTN_COMPANY_EDIT_STORAGE_RATE)
async def card_edit_storage_rate(
    message: Message, state: FSMContext
) -> None:
    data = await state.get_data()
    company = await db_comp.get_company(data.get("company_id"))
    if not company:
        return
    settings = await get_all_settings()
    default_val = float(settings.get("default_storage_rate", 20.0))
    current = (
        company["storage_rate"]
        if company["storage_rate"] is not None
        else default_val
    )
    label = _mark(company["storage_rate"] is not None)
    await _begin_edit_field(
        message, state, EditCompanyStorageRate.waiting_for_value,
        title="💵 <b>Ставка платного хранения</b>",
        current_text=f"Текущая ставка: {current} $ ({label})",
        prompt=(
            "Введите новую ставку за один период (число ≥ 0).\n"
            f"Или нажмите 🔄 Сбросить на стандартную ({default_val} $)."
        ),
    )


@router.message(
    CompaniesSection.card, F.text == BTN_COMPANY_EDIT_STORAGE_PERIOD
)
async def card_edit_storage_period(
    message: Message, state: FSMContext
) -> None:
    data = await state.get_data()
    company = await db_comp.get_company(data.get("company_id"))
    if not company:
        return
    settings = await get_all_settings()
    default_val = int(settings.get("default_storage_period_days", 30))
    current = (
        company["storage_period_days"]
        if company["storage_period_days"] is not None
        else default_val
    )
    label = _mark(company["storage_period_days"] is not None)
    await _begin_edit_field(
        message, state, EditCompanyStoragePeriod.waiting_for_value,
        title="📅 <b>Период начисления</b>",
        current_text=(
            f"Текущий период: {current} дн. "
            f"({_period_label(int(current))}, {label})"
        ),
        prompt=(
            "Введите количество дней в одном периоде (целое число ≥ 1).\n"
            "1 = ежедневный тариф, 30 = ежемесячный.\n"
            f"Или нажмите 🔄 Сбросить на стандартную ({default_val} дн.)."
        ),
    )


@router.message(CompaniesSection.card, F.text == BTN_COMPANY_RENAME)
async def card_rename(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    company_id = data.get("company_id")
    if company_id is None:
        return
    company = await db_comp.get_company(company_id)
    if not company:
        return
    await state.set_state(EditCompanyName.waiting_for_name)
    await state.update_data(company_id=company_id)
    await message.answer(
        f'✏️ Введите новое название для компании '
        f'"<b>{escape(company["name"])}</b>":',
        reply_markup=company_rename_reply_kb(),
    )


@router.message(CompaniesSection.card, F.text == BTN_COMPANY_DELETE)
async def card_delete_ask(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    company_id = data.get("company_id")
    if company_id is None:
        return
    company = await db_comp.get_company(company_id)
    if not company:
        return
    await state.set_state(CompaniesSection.confirming_delete)
    await state.update_data(company_id=company_id)
    await message.answer(
        f"⚠️ Удалить компанию «<b>{escape(company['name'])}</b>»?\n\n"
        "Все контейнеры останутся в базе, но потеряют привязку.",
        reply_markup=company_delete_confirm_reply_kb(),
    )


# ---------------------------------------------------------------------------
# Состояние: подтверждение удаления
# ---------------------------------------------------------------------------


@router.message(CompaniesSection.confirming_delete, F.text == BTN_CANCEL_X)
async def delete_cancel(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    company_id = data.get("company_id")
    if company_id is None:
        await _show_companies_list(message, state)
        return
    await _show_company_card(message, state, company_id)


@router.message(CompaniesSection.confirming_delete, F.text == BTN_CONFIRM_DELETE)
async def delete_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    company_id = data.get("company_id")
    if company_id is None:
        return
    company = await db_comp.get_company(company_id)
    if not company:
        await _show_companies_list(message, state)
        return
    name = company["name"]
    await db_comp.delete_company(company_id)
    logger.info("Компания удалена: id=%s name=%s", company_id, name)
    await message.answer(f"✅ Компания «{escape(name)}» удалена")
    await _show_companies_list(message, state)


@router.message(CompaniesSection.confirming_delete)
async def delete_fallback(message: Message) -> None:
    return


# ---------------------------------------------------------------------------
# Общая обработка выхода из редактора поля тарифа
# ---------------------------------------------------------------------------


async def _return_to_card(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    company_id = data.get("company_id")
    if company_id is None:
        await _show_companies_list(message, state)
        return
    await _show_company_card(message, state, company_id)


# ---------- Entry fee ----------


@router.message(EditCompanyEntry.waiting_for_value, F.text == BTN_CANCEL_X)
async def edit_entry_cancel(message: Message, state: FSMContext) -> None:
    await _return_to_card(message, state)


@router.message(EditCompanyEntry.waiting_for_value, F.text == BTN_RESET_DEFAULT)
async def edit_entry_reset(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await db_comp.update_entry_fee(data["company_id"], None)
    await message.answer("✅ Сброшено на стандартную")
    await _return_to_card(message, state)


@router.message(EditCompanyEntry.waiting_for_value)
async def edit_entry_value(message: Message, state: FSMContext) -> None:
    val = _parse_float(message.text)
    if val is None:
        await message.answer("❌ Введите число (например: 15 или 25.5)")
        return
    data = await state.get_data()
    await db_comp.update_entry_fee(data["company_id"], val)
    await _return_to_card(message, state)


# ---------- Free days ----------


@router.message(EditCompanyFreeDays.waiting_for_value, F.text == BTN_CANCEL_X)
async def edit_free_cancel(message: Message, state: FSMContext) -> None:
    await _return_to_card(message, state)


@router.message(
    EditCompanyFreeDays.waiting_for_value, F.text == BTN_RESET_DEFAULT
)
async def edit_free_reset(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await db_comp.update_free_days(data["company_id"], None)
    await message.answer("✅ Сброшено на стандартное")
    await _return_to_card(message, state)


@router.message(EditCompanyFreeDays.waiting_for_value)
async def edit_free_value(message: Message, state: FSMContext) -> None:
    val = _parse_int_nonneg(message.text)
    if val is None:
        await message.answer("❌ Введите целое число ≥ 0 (например: 30)")
        return
    data = await state.get_data()
    await db_comp.update_free_days(data["company_id"], val)
    await _return_to_card(message, state)


# ---------- Storage rate ----------


@router.message(EditCompanyStorageRate.waiting_for_value, F.text == BTN_CANCEL_X)
async def edit_rate_cancel(message: Message, state: FSMContext) -> None:
    await _return_to_card(message, state)


@router.message(
    EditCompanyStorageRate.waiting_for_value, F.text == BTN_RESET_DEFAULT
)
async def edit_rate_reset(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await db_comp.update_storage_rate(data["company_id"], None)
    await message.answer("✅ Сброшено на стандартную")
    await _return_to_card(message, state)


@router.message(EditCompanyStorageRate.waiting_for_value)
async def edit_rate_value(message: Message, state: FSMContext) -> None:
    val = _parse_float(message.text)
    if val is None:
        await message.answer("❌ Введите число (например: 0.5 или 20)")
        return
    data = await state.get_data()
    await db_comp.update_storage_rate(data["company_id"], val)
    await _return_to_card(message, state)


# ---------- Storage period ----------


@router.message(
    EditCompanyStoragePeriod.waiting_for_value, F.text == BTN_CANCEL_X
)
async def edit_period_cancel(message: Message, state: FSMContext) -> None:
    await _return_to_card(message, state)


@router.message(
    EditCompanyStoragePeriod.waiting_for_value, F.text == BTN_RESET_DEFAULT
)
async def edit_period_reset(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await db_comp.update_storage_period_days(data["company_id"], None)
    await message.answer("✅ Сброшено на стандартный")
    await _return_to_card(message, state)


@router.message(EditCompanyStoragePeriod.waiting_for_value)
async def edit_period_value(message: Message, state: FSMContext) -> None:
    val = _parse_int_positive(message.text)
    if val is None:
        await message.answer(
            "❌ Введите целое число ≥ 1 (1 = ежедневный, 30 = ежемесячный)"
        )
        return
    data = await state.get_data()
    await db_comp.update_storage_period_days(data["company_id"], val)
    await _return_to_card(message, state)


# ---------- Rename ----------


@router.message(EditCompanyName.waiting_for_name, F.text == BTN_CANCEL_X)
async def rename_cancel(message: Message, state: FSMContext) -> None:
    await _return_to_card(message, state)


@router.message(EditCompanyName.waiting_for_name)
async def rename_process(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        await message.answer("❌ Название должно быть от 1 до 64 символов.")
        return
    existing = await db_comp.get_company_by_name_ci(name)
    data = await state.get_data()
    company_id = data["company_id"]
    if existing and existing["id"] != company_id:
        await message.answer(f"❌ Компания «{escape(name)}» уже существует.")
        return
    await db_comp.rename_company(company_id, name)
    await _return_to_card(message, state)
