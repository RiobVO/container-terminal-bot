import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
from keyboards import BTN_COMPANIES, cancel_reply_kb, company_manage_kb, main_menu

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")


class CompanyAdd(StatesGroup):
    name = State()
    entry_fee = State()
    free_days = State()
    storage_rate = State()
    storage_period_days = State()


# ---------------------------------------------------------------------------
# Вход в меню
# ---------------------------------------------------------------------------


@router.message(F.text == BTN_COMPANIES)
async def company_menu(message: Message) -> None:
    role = await db.get_user_role(message.from_user.id)
    if role != "admin":
        await message.answer("⛔ Нет прав. Раздел доступен только администратору.")
        return
    await message.answer("Управление компаниями:", reply_markup=company_manage_kb())


# ---------------------------------------------------------------------------
# Список компаний
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "cmgr:list")
async def company_list(callback: CallbackQuery) -> None:
    companies = await db.list_companies()
    if not companies:
        await callback.answer("Компаний пока нет.", show_alert=True)
        return

    lines = ["<b>Список компаний:</b>\n"]
    for c in companies:
        lines.append(
            f"• <b>{c['name']}</b>\n"
            f"  Взнос: ${c['entry_fee']:.2f} | "
            f"Бесплатно: {c['free_days']} дн. | "
            f"Ставка: ${c['storage_rate']:.2f}/{c['storage_period_days']} дн."
        )
    await callback.message.answer("\n".join(lines))
    await callback.answer()


# ---------------------------------------------------------------------------
# Добавление компании — FSM
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "cmgr:add")
async def company_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    role = await db.get_user_role(callback.from_user.id)
    if role != "admin":
        await callback.answer("Нет прав.", show_alert=True)
        return
    await state.set_state(CompanyAdd.name)
    await callback.message.answer(
        "Введи название компании:",
        reply_markup=cancel_reply_kb(),
    )
    await callback.answer()


@router.message(CompanyAdd.name)
async def process_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым.")
        return
    existing = await db.get_company_by_name(name)
    if existing:
        await message.answer(
            f"⚠️ Компания с именем <b>{name}</b> уже существует. Введи другое название:"
        )
        return
    await state.update_data(name=name)
    await state.set_state(CompanyAdd.entry_fee)
    await message.answer(
        "Введи <b>entry_fee</b> — сумма за вход/погрузку/выгрузку в $ (например: <b>20</b>):"
    )


@router.message(CompanyAdd.entry_fee)
async def process_entry_fee(message: Message, state: FSMContext) -> None:
    val = _parse_non_negative_float(message.text)
    if val is None:
        await message.answer("❌ Введи неотрицательное число (например: 20 или 0.5).")
        return
    await state.update_data(entry_fee=val)
    await state.set_state(CompanyAdd.free_days)
    await message.answer(
        "Введи <b>free_days</b> — количество бесплатных дней хранения (например: <b>10</b>):"
    )


@router.message(CompanyAdd.free_days)
async def process_free_days(message: Message, state: FSMContext) -> None:
    val = _parse_non_negative_int(message.text)
    if val is None:
        await message.answer("❌ Введи целое неотрицательное число.")
        return
    await state.update_data(free_days=val)
    await state.set_state(CompanyAdd.storage_rate)
    await message.answer(
        "Введи <b>storage_rate</b> — ставка платного хранения в $ (например: <b>0.5</b> или <b>0</b>):"
    )


@router.message(CompanyAdd.storage_rate)
async def process_storage_rate(message: Message, state: FSMContext) -> None:
    val = _parse_non_negative_float(message.text)
    if val is None:
        await message.answer("❌ Введи неотрицательное число (например: 0.5 или 0).")
        return
    await state.update_data(storage_rate=val)
    await state.set_state(CompanyAdd.storage_period_days)
    await message.answer(
        "Введи <b>storage_period_days</b> — за сколько дней начисляется ставка "
        "(например: <b>1</b> — посуточно, <b>30</b> — раз в 30 дней):"
    )


@router.message(CompanyAdd.storage_period_days)
async def process_storage_period(message: Message, state: FSMContext) -> None:
    val = _parse_positive_int(message.text)
    if val is None:
        await message.answer("❌ Введи целое положительное число (минимум 1).")
        return

    data = await state.get_data()
    await state.clear()

    company_id = await db.add_company(
        name=data["name"],
        entry_fee=data["entry_fee"],
        free_days=data["free_days"],
        storage_rate=data["storage_rate"],
        storage_period_days=val,
    )
    logger.info(
        "Добавлена компания id=%s name=%s entry_fee=%s free_days=%s rate=%s period=%s",
        company_id, data["name"], data["entry_fee"], data["free_days"], data["storage_rate"], val,
    )
    role = await db.get_user_role(message.from_user.id)
    await message.answer(
        f"✅ Компания <b>{data['name']}</b> добавлена.\n"
        f"Взнос: ${data['entry_fee']:.2f} | "
        f"Бесплатно: {data['free_days']} дн. | "
        f"Ставка: ${data['storage_rate']:.2f}/{val} дн.",
        reply_markup=main_menu(role == "admin"),
    )


# ---------------------------------------------------------------------------
# Вспомогательные парсеры
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
