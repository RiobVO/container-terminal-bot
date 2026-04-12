import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
from keyboards import (
    BTN_COMPANIES,
    company_added_kb,
    company_back_to_list_kb,
    company_delete_confirm_kb,
    company_list_kb,
    company_view_kb,
    inline_cancel_kb,
    main_menu,
)
from utils import safe_delete

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")


class CompanyAdd(StatesGroup):
    name = State()


class CompanyTariff(StatesGroup):
    entry_fee = State()
    free_days = State()
    storage_rate = State()
    storage_period_days = State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _show_company_list(message: Message, is_admin: bool) -> None:
    """Отправляет сообщение со списком компаний."""
    companies = await db.list_companies()
    await message.answer(
        "🏢 <b>Компании</b>\n\n"
        "Выберите компанию для просмотра или добавьте новую:",
        reply_markup=company_list_kb(companies, is_admin),
    )


async def _is_admin(tg_id: int) -> bool:
    return await db.get_user_role(tg_id) == "admin"


# ---------------------------------------------------------------------------
# Вход в меню
# ---------------------------------------------------------------------------


@router.message(F.text == BTN_COMPANIES)
async def company_menu(message: Message, state: FSMContext) -> None:
    await safe_delete(message)
    await state.clear()
    is_admin = await _is_admin(message.from_user.id)
    await _show_company_list(message, is_admin)


# ---------------------------------------------------------------------------
# Навигация
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "company_list")
async def company_list_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    is_admin = await _is_admin(callback.from_user.id)
    await safe_delete(callback.message)
    await _show_company_list(callback.message, is_admin)
    await callback.answer()


@router.callback_query(F.data == "company_close")
async def company_close(callback: CallbackQuery) -> None:
    await safe_delete(callback.message)
    is_admin = await _is_admin(callback.from_user.id)
    await callback.message.answer("👌", reply_markup=main_menu(is_admin))
    await callback.answer()


@router.callback_query(F.data == "company_cancel")
async def company_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    is_admin = await _is_admin(callback.from_user.id)
    await safe_delete(callback.message)
    await _show_company_list(callback.message, is_admin)
    await callback.answer()


# ---------------------------------------------------------------------------
# Просмотр компании
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("company_view:"))
async def company_view(callback: CallbackQuery) -> None:
    company_id = int(callback.data.split(":", 1)[1])
    company = await db.get_company(company_id)
    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    is_admin = await _is_admin(callback.from_user.id)
    await safe_delete(callback.message)
    await callback.message.answer(
        f"🏢 <b>{company['name']}</b>\n\n"
        f"💵 Вход/погрузка/выгрузка: {company['entry_fee']:.2f} $\n"
        f"🆓 Бесплатных дней: {company['free_days']}\n"
        f"📦 Платное хранение: {company['storage_rate']:.2f} $ / {company['storage_period_days']} дн.",
        reply_markup=company_view_kb(company_id, is_admin),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Добавление компании
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "company_add")
async def company_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Нет прав.", show_alert=True)
        return
    await safe_delete(callback.message)
    await state.set_state(CompanyAdd.name)
    await callback.message.answer(
        "Введите название новой компании:",
        reply_markup=inline_cancel_kb(),
    )
    await callback.answer()


@router.message(CompanyAdd.name)
async def company_add_name(message: Message, state: FSMContext) -> None:
    await safe_delete(message)
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        await message.answer(
            "❌ Название должно быть от 1 до 64 символов.",
            reply_markup=inline_cancel_kb(),
        )
        return

    existing = await db.get_company_by_name_ci(name)
    if existing:
        await message.answer(
            f"⚠️ Компания «{name}» уже существует.",
            reply_markup=inline_cancel_kb(),
        )
        return

    company_id = await db.add_company(name=name)
    await state.clear()
    logger.info("Добавлена компания id=%s name=%s (дефолтный тариф)", company_id, name)

    await message.answer(
        f"✅ Компания «<b>{name}</b>» добавлена.\n\n"
        "Тариф пока не настроен. Настроить сейчас?",
        reply_markup=company_added_kb(company_id),
    )


# ---------------------------------------------------------------------------
# Настройка тарифа
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("company_tariff:"))
async def company_tariff_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Нет прав.", show_alert=True)
        return
    company_id = int(callback.data.split(":", 1)[1])
    company = await db.get_company(company_id)
    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    await safe_delete(callback.message)
    await state.set_state(CompanyTariff.entry_fee)
    await state.update_data(company_id=company_id, company_name=company["name"])
    await callback.message.answer(
        "Введите стоимость входа/погрузки/выгрузки в $ (например: <b>20</b>):",
        reply_markup=inline_cancel_kb(),
    )
    await callback.answer()


@router.message(CompanyTariff.entry_fee)
async def tariff_entry_fee(message: Message, state: FSMContext) -> None:
    await safe_delete(message)
    val = _parse_non_negative_float(message.text)
    if val is None:
        await message.answer(
            "❌ Введите неотрицательное число (например: 20 или 0.5).",
            reply_markup=inline_cancel_kb(),
        )
        return
    await state.update_data(entry_fee=val)
    await state.set_state(CompanyTariff.free_days)
    await message.answer(
        "Сколько дней бесплатного хранения? (например: <b>30</b>):",
        reply_markup=inline_cancel_kb(),
    )


@router.message(CompanyTariff.free_days)
async def tariff_free_days(message: Message, state: FSMContext) -> None:
    await safe_delete(message)
    val = _parse_non_negative_int(message.text)
    if val is None:
        await message.answer(
            "❌ Введите целое неотрицательное число.",
            reply_markup=inline_cancel_kb(),
        )
        return
    await state.update_data(free_days=val)
    await state.set_state(CompanyTariff.storage_rate)
    await message.answer(
        "Введите ставку платного хранения в $ (например: <b>0.5</b> или <b>0</b>):",
        reply_markup=inline_cancel_kb(),
    )


@router.message(CompanyTariff.storage_rate)
async def tariff_storage_rate(message: Message, state: FSMContext) -> None:
    await safe_delete(message)
    val = _parse_non_negative_float(message.text)
    if val is None:
        await message.answer(
            "❌ Введите неотрицательное число (например: 0.5 или 0).",
            reply_markup=inline_cancel_kb(),
        )
        return
    await state.update_data(storage_rate=val)
    await state.set_state(CompanyTariff.storage_period_days)
    await message.answer(
        "За сколько дней начисляется эта ставка? "
        "(например: <b>1</b> — посуточно, <b>30</b> — помесячно):",
        reply_markup=inline_cancel_kb(),
    )


@router.message(CompanyTariff.storage_period_days)
async def tariff_storage_period(message: Message, state: FSMContext) -> None:
    await safe_delete(message)
    val = _parse_positive_int(message.text)
    if val is None:
        await message.answer(
            "❌ Введите целое положительное число (минимум 1).",
            reply_markup=inline_cancel_kb(),
        )
        return

    data = await state.get_data()
    await state.clear()

    await db.update_company_tariff(
        company_id=data["company_id"],
        entry_fee=data["entry_fee"],
        free_days=data["free_days"],
        storage_rate=data["storage_rate"],
        storage_period_days=val,
    )
    logger.info(
        "Тариф обновлён: company_id=%s entry_fee=%s free_days=%s rate=%s period=%s",
        data["company_id"], data["entry_fee"], data["free_days"], data["storage_rate"], val,
    )

    await message.answer(
        f"✅ Тариф компании «<b>{data['company_name']}</b>» обновлён.",
        reply_markup=company_back_to_list_kb(),
    )


# ---------------------------------------------------------------------------
# Удаление компании
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("company_delete:"))
async def company_delete(callback: CallbackQuery) -> None:
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Нет прав.", show_alert=True)
        return
    company_id = int(callback.data.split(":", 1)[1])
    company = await db.get_company(company_id)
    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    await safe_delete(callback.message)
    await callback.message.answer(
        f"⚠️ Удалить компанию «<b>{company['name']}</b>»?\n\n"
        "Все связанные контейнеры останутся в базе, но потеряют привязку.",
        reply_markup=company_delete_confirm_kb(company_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("company_confirm_delete:"))
async def company_delete_confirm(callback: CallbackQuery) -> None:
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Нет прав.", show_alert=True)
        return
    company_id = int(callback.data.split(":", 1)[1])
    company = await db.get_company(company_id)
    if not company:
        await callback.answer("Компания уже удалена.", show_alert=True)
        return
    name = company["name"]
    await db.delete_company(company_id)
    logger.info("Компания удалена: id=%s name=%s user=%s", company_id, name, callback.from_user.id)
    await safe_delete(callback.message)
    await callback.message.answer(
        f"✅ Компания «<b>{name}</b>» удалена.",
        reply_markup=company_back_to_list_kb(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Парсеры
# ---------------------------------------------------------------------------


def _parse_non_negative_float(text: str | None) -> float | None:
    try:
        v = float((text or "").strip().replace(",", "."))
        return v if v >= 0 else None
    except ValueError:
        return None


def _parse_non_negative_int(text: str | None) -> int | None:
    try:
        v = int((text or "").strip())
        return v if v >= 0 else None
    except ValueError:
        return None


def _parse_positive_int(text: str | None) -> int | None:
    try:
        v = int((text or "").strip())
        return v if v >= 1 else None
    except ValueError:
        return None
