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
BTN_REPORT = "📊 Отчёт"
BTN_COMPANIES = "🏢 Компании"
BTN_CANCEL = "❌ Отмена"

CONTAINER_TYPES = ("20GP", "20HQ", "40GP", "40HQ", "45HQ")


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=BTN_CONTAINER), KeyboardButton(text=BTN_REPORT)],
    ]
    if is_admin:
        buttons.append([KeyboardButton(text=BTN_COMPANIES)])
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


def companies_reply_kb(companies: list) -> ReplyKeyboardMarkup:
    """Reply-клавиатура со списком компаний (по одной в ряд) + отмена."""
    buttons = [[KeyboardButton(text=c["name"])] for c in companies]
    buttons.append([KeyboardButton(text=BTN_CANCEL)])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


# ---------------------------------------------------------------------------
# Inline: типы контейнеров
# ---------------------------------------------------------------------------


def types_reply_kb() -> ReplyKeyboardMarkup:
    """Reply-клавиатура с типами контейнеров + отмена."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="20GP"), KeyboardButton(text="20HQ"), KeyboardButton(text="40GP")],
            [KeyboardButton(text="40HQ"), KeyboardButton(text="45HQ")],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        is_persistent=False,
    )


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


def after_reg_kb(number: str) -> InlineKeyboardMarkup:
    """Инлайн-кнопки после успешной регистрации: вывезти сразу или готово."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚚 Вывезти сразу", callback_data=f"reg_dep:{number}")],
            [InlineKeyboardButton(text="✅ Готово", callback_data="reg_done")],
        ]
    )


def duplicate_action_kb(number: str) -> InlineKeyboardMarkup:
    # Номер (до 12 символов) зашиваем в callback_data, чтобы не зависеть от состояния FSM
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚚 Отметить вывоз", callback_data=f"dup_dep:{number}")],
            [InlineKeyboardButton(text=BTN_CANCEL, callback_data="dup_cancel")],
        ]
    )


# ---------------------------------------------------------------------------
# Inline: раздел «Компании»
# ---------------------------------------------------------------------------


def company_list_kb(companies: list, is_admin: bool) -> InlineKeyboardMarkup:
    """Список компаний с управлением."""
    builder = InlineKeyboardBuilder()
    if is_admin:
        builder.button(text="➕ Добавить компанию", callback_data="company_add")
    for c in companies:
        builder.button(text=c["name"], callback_data=f"company_view:{c['id']}")
    builder.button(text="❌ Закрыть", callback_data="company_close")
    builder.adjust(1)
    return builder.as_markup()


def company_view_kb(company_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    """Кнопки в карточке компании."""
    buttons = []
    if is_admin:
        buttons.append([InlineKeyboardButton(text="⚙️ Изменить тариф", callback_data=f"company_tariff:{company_id}")])
        buttons.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"company_delete:{company_id}")])
    buttons.append([InlineKeyboardButton(text="↩️ К списку", callback_data="company_list")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def company_added_kb(company_id: int) -> InlineKeyboardMarkup:
    """Кнопки после добавления компании."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Настроить тариф", callback_data=f"company_tariff:{company_id}")],
        [InlineKeyboardButton(text="↩️ К списку компаний", callback_data="company_list")],
    ])


def company_delete_confirm_kb(company_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления компании."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"company_confirm_delete:{company_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"company_view:{company_id}")],
    ])


def company_back_to_list_kb() -> InlineKeyboardMarkup:
    """Кнопка возврата к списку компаний."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ К списку компаний", callback_data="company_list")],
    ])


def inline_cancel_kb() -> InlineKeyboardMarkup:
    """Инлайн-кнопка отмены для FSM-шагов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="company_cancel")],
    ])
