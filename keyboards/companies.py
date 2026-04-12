"""Клавиатуры раздела компаний — reply-first."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from keyboards.main import BTN_BACK

# Навигация
BTN_COMPANIES_BACK = "◀ К списку компаний"
BTN_ADD_COMPANY = "➕ Добавить компанию"

# Действия в карточке компании
BTN_COMPANY_EDIT_ENTRY = "💰 Изменить стоимость входа"
BTN_COMPANY_EDIT_FREE_DAYS = "🆓 Изменить бесплатные дни"
BTN_COMPANY_EDIT_STORAGE_RATE = "💵 Изменить ставку хранения"
BTN_COMPANY_EDIT_STORAGE_PERIOD = "📅 Изменить период начисления"
BTN_COMPANY_RENAME = "✏️ Изменить название"
BTN_COMPANY_DELETE = "🗑 Удалить компанию"

# Кнопки редактирования тарифа
BTN_RESET_DEFAULT = "🔄 Сбросить на стандартную"
BTN_CANCEL_X = "❌ Отмена"

# Подтверждение удаления
BTN_CONFIRM_DELETE = "✅ Да, удалить"


def companies_list_reply_kb(
    companies: list,
) -> tuple[ReplyKeyboardMarkup, dict[str, int]]:
    """Список компаний (по одной в ряд) + мэппинг текст→id для обработки.

    Ожидает строки с полями ``id``, ``name``, ``active_count`` —
    счётчик выводится в скобках всегда, включая 0. Сортировка по имени
    регистронезависимо (дублируется здесь на случай любых входных данных).
    """
    sorted_companies = sorted(companies, key=lambda c: c["name"].lower())
    rows: list[list[KeyboardButton]] = []
    mapping: dict[str, int] = {}
    for c in sorted_companies:
        count = int(c["active_count"] or 0)
        text = f"🏢 {c['name']} ({count})"
        mapping[text] = c["id"]
        rows.append([KeyboardButton(text=text)])
    rows.append([KeyboardButton(text=BTN_ADD_COMPANY)])
    rows.append([KeyboardButton(text=BTN_BACK)])
    kb = ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )
    return kb, mapping


def company_card_reply_kb() -> ReplyKeyboardMarkup:
    """Клавиатура карточки компании. Без кнопок-контейнеров —
    переход к карточке контейнера идёт через раздел «Контейнеры»."""
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=BTN_COMPANY_EDIT_ENTRY)],
        [KeyboardButton(text=BTN_COMPANY_EDIT_FREE_DAYS)],
        [KeyboardButton(text=BTN_COMPANY_EDIT_STORAGE_RATE)],
        [KeyboardButton(text=BTN_COMPANY_EDIT_STORAGE_PERIOD)],
        [KeyboardButton(text=BTN_COMPANY_RENAME)],
        [KeyboardButton(text=BTN_COMPANY_DELETE)],
        [KeyboardButton(text=BTN_COMPANIES_BACK)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def company_edit_field_reply_kb() -> ReplyKeyboardMarkup:
    """Клавиатура при редактировании одного поля тарифа компании."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_RESET_DEFAULT)],
            [KeyboardButton(text=BTN_CANCEL_X)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def company_rename_reply_kb() -> ReplyKeyboardMarkup:
    """Клавиатура при переименовании компании."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL_X)]],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def company_delete_confirm_reply_kb() -> ReplyKeyboardMarkup:
    """Подтверждение удаления компании."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONFIRM_DELETE)],
            [KeyboardButton(text=BTN_CANCEL_X)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )
