import logging
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from db import add_container, find_container, get_company, get_user_role, list_companies
from keyboards import (
    BTN_CONTAINER,
    cancel_reply_kb,
    companies_kb,
    date_kb,
    duplicate_action_kb,
    main_menu,
    types_kb,
)
from utils import format_ru_date, normalize_container_number, parse_ru_date

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")


class ContainerReg(StatesGroup):
    number = State()
    company = State()
    type = State()
    arrival = State()
    arrival_manual = State()


# ---------------------------------------------------------------------------
# Вход в сценарий
# ---------------------------------------------------------------------------


@router.message(F.text == BTN_CONTAINER)
async def start_container_reg(message: Message, state: FSMContext) -> None:
    await state.set_state(ContainerReg.number)
    await message.answer(
        "Введи номер контейнера (например: <b>TEMU 6275401</b>):",
        reply_markup=cancel_reply_kb(),
    )


# ---------------------------------------------------------------------------
# Шаг 1: номер
# ---------------------------------------------------------------------------


@router.message(ContainerReg.number)
async def process_number(message: Message, state: FSMContext) -> None:
    number = normalize_container_number(message.text or "")
    if not number:
        await message.answer(
            "❌ Неверный формат. Пример: <b>TEMU 6275401</b>\n"
            "4 заглавные латинские буквы + 7 цифр."
        )
        return

    # Проверка дубликата
    existing = await find_container(number)
    if existing:
        company_name = existing["company_name"]
        arrival = format_ru_date(existing["arrival_date"])
        if existing["departure_date"]:
            departure = format_ru_date(existing["departure_date"])
            await message.answer(
                f"ℹ️ Контейнер <b>{number}</b> уже зарегистрирован и вывезен.\n"
                f"Компания: <b>{company_name}</b>\n"
                f"Дата прибытия: {arrival}\n"
                f"✅ Вывезен: {departure}",
                reply_markup=main_menu(await _is_admin(message.from_user.id)),
            )
            await state.clear()
        else:
            await state.clear()
            await message.answer(
                f"ℹ️ Контейнер <b>{number}</b> уже есть в базе.\n"
                f"Компания: <b>{company_name}</b>\n"
                f"Дата прибытия: {arrival}\n"
                f"❌ Статус: не вывезен\n\n"
                f"Хочешь отметить вывоз?",
                reply_markup=duplicate_action_kb(number),
            )
        return

    # Новый контейнер — идём дальше
    companies = await list_companies()
    if not companies:
        await message.answer(
            "⚠️ Сначала администратор должен добавить хотя бы одну компанию.",
            reply_markup=main_menu(await _is_admin(message.from_user.id)),
        )
        await state.clear()
        return

    await state.update_data(number=number)
    await state.set_state(ContainerReg.company)
    await message.answer(
        "Выбери компанию:",
        reply_markup=companies_kb(companies, "reg_company"),
    )


# ---------------------------------------------------------------------------
# Callback: кнопка «Отметить вывоз» при дубликате
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("dup_dep:"))
async def dup_start_departure(callback: CallbackQuery, state: FSMContext) -> None:
    # Импортируем здесь, чтобы избежать циклических импортов
    from handlers.departure import DepartureFlow, ask_departure_date

    number = callback.data.split(":", 1)[1]
    # Проверяем, что контейнер до сих пор не вывезен (защита от гонок)
    existing = await find_container(number)
    if not existing:
        await callback.answer("Контейнер не найден.", show_alert=True)
        return
    if existing["departure_date"]:
        await callback.answer("Контейнер уже вывезен.", show_alert=True)
        return

    await state.clear()
    await state.set_state(DepartureFlow.date)
    await state.update_data(number=number)
    await callback.message.edit_reply_markup()
    await ask_departure_date(callback.message, number)
    await callback.answer()


@router.callback_query(F.data == "dup_cancel")
async def dup_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        "Отменено.",
        reply_markup=main_menu(await _is_admin(callback.from_user.id)),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 2: выбор компании
# ---------------------------------------------------------------------------


@router.callback_query(ContainerReg.company, F.data.startswith("reg_company:"))
async def process_company(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "cancel":
        await state.clear()
        await callback.message.edit_reply_markup()
        await callback.message.answer(
            "Отменено.",
            reply_markup=main_menu(await _is_admin(callback.from_user.id)),
        )
        await callback.answer()
        return

    company_id = int(value)
    await state.update_data(company_id=company_id)
    await state.set_state(ContainerReg.type)
    await callback.message.edit_reply_markup()
    await callback.message.answer("Выбери тип контейнера:", reply_markup=types_kb("reg_type"))
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 3: выбор типа
# ---------------------------------------------------------------------------


@router.callback_query(ContainerReg.type, F.data.startswith("reg_type:"))
async def process_type(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "cancel":
        await state.clear()
        await callback.message.edit_reply_markup()
        await callback.message.answer(
            "Отменено.",
            reply_markup=main_menu(await _is_admin(callback.from_user.id)),
        )
        await callback.answer()
        return

    await state.update_data(container_type=value)
    await state.set_state(ContainerReg.arrival)
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        "Укажи дату прибытия:",
        reply_markup=date_kb("reg_arrival"),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 4a: выбор даты (сегодня или вручную)
# ---------------------------------------------------------------------------


@router.callback_query(ContainerReg.arrival, F.data.startswith("reg_arrival:"))
async def process_arrival_choice(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    await callback.message.edit_reply_markup()

    if value == "cancel":
        await state.clear()
        await callback.message.answer(
            "Отменено.",
            reply_markup=main_menu(await _is_admin(callback.from_user.id)),
        )
        await callback.answer()
        return

    if value == "today":
        await _save_container(callback.message, state, date.today(), callback.from_user.id)
        await callback.answer()
    elif value == "manual":
        await state.set_state(ContainerReg.arrival_manual)
        await callback.message.answer(
            "Введи дату прибытия в формате <b>ДД.ММ.ГГГГ</b>:",
            reply_markup=cancel_reply_kb(),
        )
        await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 4b: ручной ввод даты
# ---------------------------------------------------------------------------


@router.message(ContainerReg.arrival_manual)
async def process_arrival_manual(message: Message, state: FSMContext) -> None:
    d = parse_ru_date(message.text or "")
    if not d:
        await message.answer(
            "❌ Неверный формат даты. Пример: <b>11.04.2026</b>"
        )
        return
    await _save_container(message, state, d, message.from_user.id)


# ---------------------------------------------------------------------------
# Сохранение
# ---------------------------------------------------------------------------


async def _save_container(
    message: Message,
    state: FSMContext,
    arrival: date,
    user_id: int,
) -> None:
    data = await state.get_data()
    number = data["number"]
    company_id = data["company_id"]
    container_type = data["container_type"]

    company = await get_company(company_id)

    result = await add_container(number, company_id, container_type, arrival)
    await state.clear()
    is_admin = await _is_admin(user_id)

    if result is None:
        await message.answer(
            f"⚠️ Контейнер <b>{number}</b> уже существует в базе (гонка записи).",
            reply_markup=main_menu(is_admin),
        )
        return

    await message.answer(
        f"✅ Контейнер <b>{number}</b> ({container_type}) зарегистрирован.\n"
        f"Компания: <b>{company['name']}</b>\n"
        f"Дата прибытия: {format_ru_date(arrival)}",
        reply_markup=main_menu(is_admin),
    )


async def _is_admin(tg_id: int) -> bool:
    return await get_user_role(tg_id) == "admin"
