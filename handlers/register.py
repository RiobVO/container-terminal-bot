"""FSM регистрации нового контейнера — reply-first.

Шаги:
1. Ввод номера (приходит извне — из handlers/containers.py).
2. Выбор компании (reply: список существующих + ввод нового названия).
3. Выбор даты прибытия: «Сегодня» / «Ещё в пути» / «Ввести дату вручную».
4. Выбор типа контейнера.
5. Сохранение в БД + подтверждение + карточка.
"""
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from db import companies as db_comp
from db import containers as db_cont
from keyboards.containers import CONTAINER_TYPES
from keyboards.main import main_menu
from keyboards.register import (
    BTN_ARRIVAL_MANUAL,
    BTN_ARRIVAL_TODAY,
    BTN_ARRIVAL_TRANSIT,
    BTN_REG_CANCEL,
    BTN_REG_SKIP_TYPE,
    register_arrival_date_reply_kb,
    register_company_reply_kb,
    register_manual_date_reply_kb,
    register_type_reply_kb,
)
from states import RegisterContainer

logger = logging.getLogger(__name__)
router = Router()


# ---------------------------------------------------------------------------
# Точка входа (вызывается из handlers/containers.py)
# ---------------------------------------------------------------------------


async def start_registration(
    message: Message,
    state: FSMContext,
    normalized: str,
    display: str,
) -> None:
    """Начинает флоу регистрации нового контейнера."""
    companies = await db_comp.list_companies()

    await state.set_state(RegisterContainer.waiting_for_company)
    await state.update_data(number=normalized, display_number=display)

    kb = register_company_reply_kb([c["name"] for c in companies])

    await message.answer(
        f"📦 <b>Оформление прибытия контейнера {display}</b>\n\n"
        "Выберите компанию из списка или введите название новой:",
        reply_markup=kb,
    )


async def _cancel_and_go_home(
    message: Message, state: FSMContext, role: str
) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu(role))


# ---------------------------------------------------------------------------
# Шаг 1: выбор / создание компании
# ---------------------------------------------------------------------------


@router.message(
    RegisterContainer.waiting_for_company, F.text == BTN_REG_CANCEL
)
async def company_cancel(
    message: Message, state: FSMContext, role: str
) -> None:
    """Выход из флоу регистрации на шаге выбора компании.

    Без этого обработчика любой текст в этом состоянии трактовался бы
    как название новой компании, и случайный ввод создавал бы пустую
    компанию с мусорным именем.
    """
    await _cancel_and_go_home(message, state, role)


@router.message(RegisterContainer.waiting_for_company)
async def process_company(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ Введите название компании.")
        return

    company = await db_comp.get_company_by_name_ci(name)
    if company:
        company_id = company["id"]
        company_name = company["name"]
    else:
        company_id = await db_comp.add_company(name=name)
        company_name = name
        logger.info(
            "Новая компания при регистрации: %s (id=%s)", name, company_id
        )

    await state.update_data(company_id=company_id, company_name=company_name)
    await state.set_state(RegisterContainer.waiting_for_arrival_date)

    data = await state.get_data()
    display = data["display_number"]

    await message.answer(
        f"📦 Контейнер <b>{display}</b>\n"
        f"🏢 Компания: <b>{company_name}</b>\n\n"
        "Когда контейнер прибыл на терминал?",
    )
    await message.answer(
        "Выберите дату:",
        reply_markup=register_arrival_date_reply_kb(),
    )


# ---------------------------------------------------------------------------
# Шаг 2: дата прибытия (reply)
# ---------------------------------------------------------------------------


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def _go_to_type_step(message: Message, state: FSMContext) -> None:
    await state.set_state(RegisterContainer.waiting_for_type)
    await message.answer(
        "📦 Выберите тип контейнера:",
        reply_markup=register_type_reply_kb(),
    )


@router.message(
    RegisterContainer.waiting_for_arrival_date, F.text == BTN_REG_CANCEL
)
async def arrival_cancel(
    message: Message, state: FSMContext, role: str
) -> None:
    await _cancel_and_go_home(message, state, role)


@router.message(
    RegisterContainer.waiting_for_arrival_date, F.text == BTN_ARRIVAL_TODAY
)
async def arrival_today(message: Message, state: FSMContext) -> None:
    await state.update_data(status="on_terminal", arrival_date=_now_str())
    await _go_to_type_step(message, state)


@router.message(
    RegisterContainer.waiting_for_arrival_date, F.text == BTN_ARRIVAL_TRANSIT
)
async def arrival_transit(message: Message, state: FSMContext) -> None:
    await state.update_data(status="in_transit", arrival_date=None)
    await _go_to_type_step(message, state)


@router.message(
    RegisterContainer.waiting_for_arrival_date, F.text == BTN_ARRIVAL_MANUAL
)
async def arrival_manual_prompt(
    message: Message, state: FSMContext
) -> None:
    await state.set_state(RegisterContainer.waiting_for_manual_date)
    await message.answer(
        "Введите дату прибытия в формате <b>ДД.ММ.ГГГГ</b>\n"
        "Например: 15.03.2026",
        reply_markup=register_manual_date_reply_kb(),
    )


@router.message(RegisterContainer.waiting_for_arrival_date)
async def arrival_fallback(message: Message) -> None:
    await message.answer("Выберите вариант из кнопок ниже.")


# ---------- Подсостояние: ручной ввод даты ----------


@router.message(
    RegisterContainer.waiting_for_manual_date, F.text == BTN_REG_CANCEL
)
async def manual_date_cancel(
    message: Message, state: FSMContext, role: str
) -> None:
    await _cancel_and_go_home(message, state, role)


@router.message(RegisterContainer.waiting_for_manual_date)
async def manual_date_process(
    message: Message, state: FSMContext
) -> None:
    text = (message.text or "").strip()
    try:
        parsed = datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        await message.answer("❌ Неверный формат. Пример: <b>15.03.2026</b>")
        return

    if parsed.date() > datetime.now().date():
        await message.answer("❌ Дата прибытия не может быть в будущем.")
        return

    arrival_str = parsed.strftime("%Y-%m-%d %H:%M:%S")
    await state.update_data(status="on_terminal", arrival_date=arrival_str)
    await _go_to_type_step(message, state)


# ---------------------------------------------------------------------------
# Шаг 3: тип контейнера (reply)
# ---------------------------------------------------------------------------


@router.message(RegisterContainer.waiting_for_type, F.text == BTN_REG_CANCEL)
async def type_cancel(
    message: Message, state: FSMContext, role: str
) -> None:
    await _cancel_and_go_home(message, state, role)


@router.message(RegisterContainer.waiting_for_type, F.text == BTN_REG_SKIP_TYPE)
async def type_skip(message: Message, state: FSMContext, role: str) -> None:
    await _finalize(message, state, role, container_type=None)


@router.message(
    RegisterContainer.waiting_for_type, F.text.in_(CONTAINER_TYPES)
)
async def type_selected(
    message: Message, state: FSMContext, role: str
) -> None:
    await _finalize(message, state, role, container_type=message.text)


@router.message(RegisterContainer.waiting_for_type)
async def type_fallback(message: Message) -> None:
    await message.answer(
        "Выберите тип из кнопок ниже или нажмите «Пропустить»."
    )


# ---------------------------------------------------------------------------
# Финальное сохранение
# ---------------------------------------------------------------------------


def _fmt_arrival_display(arrival: str | None) -> str:
    if not arrival:
        return "—"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(arrival, fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return arrival


async def _finalize(
    message: Message,
    state: FSMContext,
    role: str,
    container_type: str | None,
) -> None:
    data = await state.get_data()
    number = data["number"]
    display = data["display_number"]
    company_id = data["company_id"]
    company_name = data["company_name"]
    status = data["status"]
    arrival_date = data.get("arrival_date")

    container_id = await db_cont.add_container(
        number=number,
        display_number=display,
        company_id=company_id,
        status=status,
        arrival_date=arrival_date,
        container_type=container_type,
    )

    if container_id is None:
        # Дубликат (race между pre-check и INSERT) — сообщаем юзеру и
        # открываем карточку уже существующего контейнера.
        await state.clear()
        await message.answer(
            f"⚠️ Контейнер <b>{display}</b> уже зарегистрирован.",
            reply_markup=main_menu(role),
        )
        existing = await db_cont.find_by_number(number)
        if existing:
            from handlers.containers import _send_container_card
            await _send_container_card(
                message, existing, state, source="active", role=role
            )
        return

    await state.clear()

    reg_dt = datetime.now().strftime("%d.%m.%Y %H:%M")
    type_line = container_type if container_type else "не указан"

    if status == "on_terminal":
        arrival_line = (
            f"📅 Дата прибытия: {_fmt_arrival_display(arrival_date)}"
        )
        status_suffix = ""
    else:
        arrival_line = (
            "⏳ Контейнер ещё не прибыл. Billing начнётся после прибытия."
        )
        status_suffix = ""

    await message.answer(
        f"✅ Контейнер <b>{display}</b> зарегистрирован\n\n"
        f"🏢 Компания: <b>{company_name}</b>\n"
        f"📦 Тип: {type_line}\n"
        f"📅 Дата регистрации: {reg_dt}\n"
        f"{arrival_line}"
        f"{status_suffix}",
        reply_markup=main_menu(role),
    )

    container = await db_cont.get_container(container_id)
    if container:
        from handlers.containers import _send_container_card
        await _send_container_card(
            message, container, state, source="active", role=role
        )

    # Live-лента: уведомление в группы
    if hasattr(message.bot, "_group_ids") and message.bot._group_ids:
        from services.group_notify import notify_groups
        username = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.full_name or "Unknown")
        status_text = "На терминале" if status == "on_terminal" else "В пути"
        notify_text = (
            f"📥 <b>Новый контейнер</b>\n"
            f"{display} ({company_name}) — {container_type or 'тип не указан'}\n"
            f"Статус: {status_text}\n"
            f"Оператор: {username}"
        )
        await notify_groups(message.bot, message.bot._group_ids, notify_text)
