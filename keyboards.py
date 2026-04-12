from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils import months_list

# ---------------------------------------------------------------------------
# Тексты кнопок главного меню
# ---------------------------------------------------------------------------
BTN_CONTAINER = "📦 Контейнер"
BTN_DEPARTURE = "🚚 Вывоз"
BTN_REPORT = "📊 Отчёт"
BTN_COMPANIES = "🏢 Компании"
BTN_CANCEL = "❌ Отмена"

CONTAINER_TYPES = ("20GP", "20HQ", "40GP", "40HQ", "45HQ")


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=BTN_CONTAINER), KeyboardButton(text=BTN_DEPARTURE)],
        [KeyboardButton(text=BTN_REPORT)],
    ]
    if is_admin:
        buttons[1].append(KeyboardButton(text=BTN_COMPANIES))
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def cancel_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


# ---------------------------------------------------------------------------
# Inline: компании
# ---------------------------------------------------------------------------


def companies_kb(companies: list, prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for c in companies:
        builder.button(text=c["name"], callback_data=f"{prefix}:{c['id']}")
    builder.button(text=BTN_CANCEL, callback_data=f"{prefix}:cancel")
    builder.adjust(1)
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Inline: типы контейнеров
# ---------------------------------------------------------------------------


def types_kb(prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in CONTAINER_TYPES:
        builder.button(text=t, callback_data=f"{prefix}:{t}")
    builder.button(text=BTN_CANCEL, callback_data=f"{prefix}:cancel")
    builder.adjust(3, 2, 1)
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Inline: выбор даты (сегодня / вручную)
# ---------------------------------------------------------------------------


def date_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Пропустить (сегодня)", callback_data=f"{prefix}:today")],
            [InlineKeyboardButton(text="✏️ Ввести вручную", callback_data=f"{prefix}:manual")],
            [InlineKeyboardButton(text=BTN_CANCEL, callback_data=f"{prefix}:cancel")],
        ]
    )


# ---------------------------------------------------------------------------
# Inline: месяцы
# ---------------------------------------------------------------------------


def months_kb(prefix: str, n: int = 12) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ym in months_list(n):
        year, month = ym.split("-")
        builder.button(text=f"{month}.{year}", callback_data=f"{prefix}:{ym}")
    builder.button(text=BTN_CANCEL, callback_data=f"{prefix}:cancel")
    builder.adjust(3)
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Inline: вид отчёта
# ---------------------------------------------------------------------------


def report_kind_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все контейнеры", callback_data=f"{prefix}:all")],
            [InlineKeyboardButton(text="✅ Только вывезенные", callback_data=f"{prefix}:departed")],
            [InlineKeyboardButton(text=BTN_CANCEL, callback_data=f"{prefix}:cancel")],
        ]
    )


# ---------------------------------------------------------------------------
# Inline: действия с дубликатом
# ---------------------------------------------------------------------------


def duplicate_action_kb(number: str) -> InlineKeyboardMarkup:
    # Номер (до 12 символов) зашиваем в callback_data, чтобы не зависеть от состояния FSM
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚚 Отметить вывоз", callback_data=f"dup_dep:{number}")],
            [InlineKeyboardButton(text=BTN_CANCEL, callback_data="dup_cancel")],
        ]
    )


# ---------------------------------------------------------------------------
# Inline: компании-меню для управления (admin)
# ---------------------------------------------------------------------------


def company_manage_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить компанию", callback_data="cmgr:add")],
            [InlineKeyboardButton(text="📋 Список компаний", callback_data="cmgr:list")],
        ]
    )
