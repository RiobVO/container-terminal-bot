"""Главное меню бота."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

BTN_CONTAINERS = "📦 Контейнеры"
BTN_COMPANIES = "🏢 Компании"
BTN_REPORTS = "📊 Отчёты"
BTN_SETTINGS = "⚙️ Настройки"
BTN_BACK = "◀ Назад"


def main_menu(role: str) -> ReplyKeyboardMarkup:
    """Главное меню в зависимости от роли."""
    if role == "reports_only":
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BTN_REPORTS)]],
            resize_keyboard=True,
            is_persistent=True,
        )

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONTAINERS), KeyboardButton(text=BTN_COMPANIES)],
            [KeyboardButton(text=BTN_REPORTS), KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    """Убирает reply-клавиатуру."""
    return ReplyKeyboardRemove()
