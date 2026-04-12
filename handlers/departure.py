import logging
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from db import find_container, get_company, get_user_role, set_departure
from keyboards import BTN_DEPARTURE, cancel_reply_kb, date_kb, main_menu
from utils import calculate_total, format_ru_date, normalize_container_number, parse_ru_date

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")


class DepartureFlow(StatesGroup):
    number = State()
    date = State()
    date_manual = State()


# ---------------------------------------------------------------------------
# Вход в сценарий
# ---------------------------------------------------------------------------


@router.message(F.text == BTN_DEPARTURE)
async def start_departure(message: Message, state: FSMContext) -> None:
    await state.set_state(DepartureFlow.number)
    await message.answer(
        "Введи номер контейнера для отметки вывоза:",
        reply_markup=cancel_reply_kb(),
    )


# ---------------------------------------------------------------------------
# Шаг 1: номер
# ---------------------------------------------------------------------------


@router.message(DepartureFlow.number)
async def process_number(message: Message, state: FSMContext) -> None:
    number = normalize_container_number(message.text or "")
    if not number:
        await message.answer(
            "❌ Неверный формат. Пример: <b>TEMU 6275401</b>"
        )
        return

    row = await find_container(number)
    if not row:
        await state.clear()
        role = await get_user_role(message.from_user.id)
        await message.answer(
            f"❌ Контейнер <b>{number}</b> не найден в базе.",
            reply_markup=main_menu(role == "admin"),
        )
        return

    if row["departure_date"]:
        await state.clear()
        role = await get_user_role(message.from_user.id)
        await message.answer(
            f"ℹ️ Контейнер <b>{number}</b> уже вывезен "
            f"{format_ru_date(row['departure_date'])}.",
            reply_markup=main_menu(role == "admin"),
        )
        return

    await state.update_data(number=number)
    await state.set_state(DepartureFlow.date)
    await ask_departure_date(message, number)


# ---------------------------------------------------------------------------
# Вспомогательная функция — используется и из container.py при дубликате
# ---------------------------------------------------------------------------


async def ask_departure_date(message: Message, number: str) -> None:
    await message.answer(
        f"Укажи дату вывоза контейнера <b>{number}</b>:",
        reply_markup=date_kb("dep_date"),
    )


# ---------------------------------------------------------------------------
# Шаг 2a: выбор «сегодня» или «вручную»
# ---------------------------------------------------------------------------


@router.callback_query(DepartureFlow.date, F.data.startswith("dep_date:"))
async def process_date_choice(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    await callback.message.edit_reply_markup()

    if value == "cancel":
        await state.clear()
        role = await get_user_role(callback.from_user.id)
        await callback.message.answer(
            "Отменено.",
            reply_markup=main_menu(role == "admin"),
        )
        await callback.answer()
        return

    if value == "today":
        await _apply_departure(callback.message, state, date.today(), callback.from_user.id)
        await callback.answer()
    elif value == "manual":
        await state.set_state(DepartureFlow.date_manual)
        await callback.message.answer(
            "Введи дату вывоза в формате <b>ДД.ММ.ГГГГ</b>:",
            reply_markup=cancel_reply_kb(),
        )
        await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 2b: ручной ввод даты
# ---------------------------------------------------------------------------


@router.message(DepartureFlow.date_manual)
async def process_date_manual(message: Message, state: FSMContext) -> None:
    d = parse_ru_date(message.text or "")
    if not d:
        await message.answer(
            "❌ Неверный формат даты. Пример: <b>11.04.2026</b>"
        )
        return
    await _apply_departure(message, state, d, message.from_user.id)


# ---------------------------------------------------------------------------
# Применение вывоза
# ---------------------------------------------------------------------------


async def _apply_departure(
    message: Message,
    state: FSMContext,
    departure: date,
    user_id: int,
) -> None:
    data = await state.get_data()
    number = data.get("number")
    await state.clear()

    ok = await set_departure(number, departure)
    role = await get_user_role(user_id)
    is_admin = role == "admin"

    if not ok:
        await message.answer(
            f"⚠️ Не удалось зафиксировать вывоз для <b>{number}</b>. "
            f"Контейнер уже вывезен или не существует.",
            reply_markup=main_menu(is_admin),
        )
        return

    # Рассчитываем итоговую сумму для обратной связи
    row = await find_container(number)
    company = await get_company(row["company_id"])
    arrival = date.fromisoformat(row["arrival_date"])
    days, total = calculate_total(
        arrival, departure,
        company["entry_fee"], company["free_days"],
        company["storage_rate"], company["storage_period_days"],
    )

    await message.answer(
        f"✅ Вывоз зафиксирован: <b>{number}</b>\n"
        f"Дата вывоза: {format_ru_date(departure)}\n"
        f"Дней хранения: <b>{days}</b>\n"
        f"Сумма к оплате: <b>${total:.2f}</b>",
        reply_markup=main_menu(is_admin),
    )
