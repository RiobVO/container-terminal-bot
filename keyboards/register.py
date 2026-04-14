"""Клавиатуры FSM регистрации нового контейнера — reply-first."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from keyboards.containers import CONTAINER_TYPES

# Выбор даты прибытия
BTN_ARRIVAL_TODAY = "📅 Сегодня"
BTN_ARRIVAL_TRANSIT = "🚚 Ещё в пути"
BTN_ARRIVAL_MANUAL = "✏️ Ввести дату вручную"

# Тип контейнера
BTN_REG_SKIP_TYPE = "⏭ Пропустить"

# Общий cancel для FSM регистрации
BTN_REG_CANCEL = "◀ Отмена"


def register_company_reply_kb(
    company_names: list[str],
) -> ReplyKeyboardMarkup:
    """Список существующих компаний + кнопка отмены.

    Отмена добавляется отдельной строкой внизу, чтобы юзер мог выйти из
    флоу регистрации если ввёл номер контейнера по ошибке. Без этой
    кнопки любой текст трактуется как название новой компании — юзер
    может случайно создать пустую компанию с мусорным именем.
    """
    rows: list[list[KeyboardButton]] = []
    buttons = [KeyboardButton(text=name) for name in company_names]
    for i in range(0, len(buttons), 2):
        row = [buttons[i]]
        if i + 1 < len(buttons):
            row.append(buttons[i + 1])
        rows.append(row)
    rows.append([KeyboardButton(text=BTN_REG_CANCEL)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def register_arrival_date_reply_kb() -> ReplyKeyboardMarkup:
    """Выбор даты прибытия при регистрации контейнера."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ARRIVAL_TODAY)],
            [KeyboardButton(text=BTN_ARRIVAL_TRANSIT)],
            [KeyboardButton(text=BTN_ARRIVAL_MANUAL)],
            [KeyboardButton(text=BTN_REG_CANCEL)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def register_manual_date_reply_kb() -> ReplyKeyboardMarkup:
    """Клавиатура подсостояния ручного ввода даты."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_REG_CANCEL)]],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def register_type_reply_kb() -> ReplyKeyboardMarkup:
    """Выбор типа контейнера при регистрации."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=CONTAINER_TYPES[0]),
                KeyboardButton(text=CONTAINER_TYPES[1]),
                KeyboardButton(text=CONTAINER_TYPES[2]),
            ],
            [
                KeyboardButton(text=CONTAINER_TYPES[3]),
                KeyboardButton(text=CONTAINER_TYPES[4]),
            ],
            [KeyboardButton(text=BTN_REG_SKIP_TYPE)],
            [KeyboardButton(text=BTN_REG_CANCEL)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )
