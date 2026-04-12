"""Клавиатуры раздела отчётов — reply-first."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from keyboards.main import BTN_BACK

# Тексты трёх типов отчёта
BTN_REP_ACTIVE = "🟢 Активные контейнеры"
BTN_REP_MIXED = "📋 Активные + вывезенные"
BTN_REP_DEPARTED = "🔴 Только вывезенные"

# Режим генерации
BTN_SCOPE_ALL = "🌐 По всем компаниям"
BTN_SCOPE_COMPANY = "🏢 По одной компании"


def reports_type_reply_kb() -> ReplyKeyboardMarkup:
    """Меню выбора типа отчёта (первый экран раздела)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_REP_ACTIVE)],
            [KeyboardButton(text=BTN_REP_MIXED)],
            [KeyboardButton(text=BTN_REP_DEPARTED)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def reports_scope_reply_kb() -> ReplyKeyboardMarkup:
    """Меню выбора режима (по всем компаниям / по одной компании)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SCOPE_ALL)],
            [KeyboardButton(text=BTN_SCOPE_COMPANY)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def report_company_select_reply_kb(companies: list) -> ReplyKeyboardMarkup:
    """Выбор компании для отчёта (по одной в ряд, алфавит + ◀ Назад)."""
    sorted_companies = sorted(companies, key=lambda c: c["name"].lower())
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=f"🏢 {c['name']}")] for c in sorted_companies
    ]
    rows.append([KeyboardButton(text=BTN_BACK)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )
