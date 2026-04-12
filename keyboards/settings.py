"""Клавиатуры раздела настроек — reply-first."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from keyboards.main import BTN_BACK

# Главный экран настроек
BTN_SET_USERS = "👥 Пользователи и роли"
BTN_SET_DEFAULTS = "💰 Стандартные тарифы"

# Смена роли пользователя
BTN_ROLE_FULL = "✅ Полный доступ"
BTN_ROLE_REPORTS = "📊 Только отчёты"
BTN_ROLE_NONE = "⛔ Нет доступа"
BTN_CANCEL_BACK = "◀ Отмена"

# Стандартные тарифы
BTN_DEF_ENTRY = "💵 Стоимость входа"
BTN_DEF_FREE = "🆓 Бесплатные дни"
BTN_DEF_STORAGE_RATE = "💰 Ставка хранения"
BTN_DEF_STORAGE_PERIOD = "📅 Период начисления"

# Иконки ролей
ROLE_ICONS = {"full": "✅", "reports_only": "📊", "none": "⛔"}
ROLE_NAMES = {
    "full": "Полный доступ",
    "reports_only": "Только отчёты",
    "none": "Нет доступа",
}


def settings_reply_kb() -> ReplyKeyboardMarkup:
    """Главный экран настроек."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_SET_USERS),
                KeyboardButton(text=BTN_SET_DEFAULTS),
            ],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _user_button_text(user, admin_ids: frozenset[int]) -> str:
    """Формирует текст кнопки пользователя."""
    icon = ROLE_ICONS.get(user["role"], "❓")
    display = user["full_name"] or (
        f"@{user['username']}" if user["username"] else str(user["tg_id"])
    )
    protected = " 🔒" if user["tg_id"] in admin_ids else ""
    return f"{icon} {display}{protected}"


def users_list_reply_kb(
    users: list,
    admin_ids: frozenset[int],
) -> tuple[ReplyKeyboardMarkup, dict[str, int]]:
    """Список пользователей + мэппинг текст→tg_id."""
    rows: list[list[KeyboardButton]] = []
    mapping: dict[str, int] = {}
    for u in users:
        text = _user_button_text(u, admin_ids)
        mapping[text] = u["tg_id"]
        rows.append([KeyboardButton(text=text)])

    rows.append([KeyboardButton(text=BTN_SET_DEFAULTS)])
    rows.append([KeyboardButton(text=BTN_BACK)])

    kb = ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )
    return kb, mapping


def user_role_reply_kb() -> ReplyKeyboardMarkup:
    """Клавиатура выбора роли."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ROLE_FULL)],
            [KeyboardButton(text=BTN_ROLE_REPORTS)],
            [KeyboardButton(text=BTN_ROLE_NONE)],
            [KeyboardButton(text=BTN_CANCEL_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def defaults_reply_kb() -> ReplyKeyboardMarkup:
    """Экран стандартных тарифов."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_DEF_ENTRY)],
            [KeyboardButton(text=BTN_DEF_FREE)],
            [KeyboardButton(text=BTN_DEF_STORAGE_RATE)],
            [KeyboardButton(text=BTN_DEF_STORAGE_PERIOD)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def default_edit_reply_kb() -> ReplyKeyboardMarkup:
    """Клавиатура при редактировании стандартного параметра."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL_BACK)]],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )
