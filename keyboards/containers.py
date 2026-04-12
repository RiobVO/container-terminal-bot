"""Клавиатуры раздела контейнеров — reply-first."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from keyboards.main import BTN_BACK

CONTAINER_TYPES: tuple[str, ...] = ("20GP", "20HQ", "40GP", "40HQ", "45HQ")

# Главный экран раздела
BTN_ADD_CONTAINER = "➕ Добавить контейнер"
BTN_SEARCH_BY_TYPE = "🔍 Найти по типу"

# Навигация
BTN_CARD_BACK_ACTIVE = "◀ К списку"

# Действия в карточке
BTN_ARRIVED = "📤 Прибыл на терминал"
BTN_DEPART = "📤 Контейнер вывезен"
BTN_UNDEPART = "↩️ Отменить вывоз"
BTN_EDIT_DEPARTURE_DATE = "📅 Изменить дату вывоза"
BTN_CHANGE_NUMBER = "✏️ Изменить номер"
BTN_CHANGE_TYPE = "📦 Изменить тип"
BTN_CHANGE_COMPANY = "🏢 Сменить компанию"
BTN_DELETE = "🗑 Удалить запись"

# Поток выбора даты вывоза. Тексты совпадают с кнопками FSM регистрации
# (📅 Сегодня / ✏️ Ввести дату вручную / ◀ Отмена), но это разные
# логические сущности — у каждой свой набор хэндлеров и состояний.
BTN_DEPART_TODAY = "📅 Сегодня"
BTN_DEPART_MANUAL = "✏️ Ввести дату вручную"
BTN_DEPART_CANCEL = "◀ Отмена"

# Подтверждения
BTN_CONFIRM_DELETE = "✅ Да, удалить"
BTN_CANCEL = "❌ Отмена"

# Набор системных текстов, которые никогда не должны попадать в валидатор
# номера контейнера. Любой текстовый хэндлер раздела «Контейнеры» должен
# в первую очередь проверять вхождение в это множество.
#
# Сюда включены также статические тексты из разделов «Компании», «Настройки»,
# «Пользователи» и «Стандартные тарифы» — на случай, если такой текст каким-то
# образом попадёт в контекст раздела контейнеров.
RESERVED_BUTTON_TEXTS: frozenset[str] = frozenset({
    # Раздел «Контейнеры»
    BTN_BACK,
    BTN_ADD_CONTAINER,
    BTN_SEARCH_BY_TYPE,
    BTN_CARD_BACK_ACTIVE,
    BTN_ARRIVED,
    BTN_DEPART,
    BTN_UNDEPART,
    BTN_EDIT_DEPARTURE_DATE,
    BTN_DEPART_TODAY,
    BTN_DEPART_MANUAL,
    BTN_DEPART_CANCEL,
    BTN_CHANGE_NUMBER,
    BTN_CHANGE_TYPE,
    BTN_CHANGE_COMPANY,
    BTN_DELETE,
    BTN_CONFIRM_DELETE,
    BTN_CANCEL,
    *CONTAINER_TYPES,
    # Раздел «Компании»
    "◀ К списку компаний",
    "➕ Добавить компанию",
    "💰 Изменить стоимость входа",
    "🆓 Изменить бесплатные дни",
    "💵 Изменить ставку хранения",
    "📅 Изменить период начисления",
    "✏️ Изменить название",
    "🗑 Удалить компанию",
    "🔄 Сбросить на стандартную",
    # Раздел «Настройки» / «Пользователи и роли» / «Стандартные тарифы»
    "👥 Пользователи и роли",
    "💰 Стандартные тарифы",
    "✅ Полный доступ",
    "📊 Только отчёты",
    "⛔ Нет доступа",
    "💵 Стоимость входа",
    "🆓 Бесплатные дни",
    "💰 Ставка хранения",
    "📅 Период начисления",
    "◀ Отмена",
    # FSM регистрации нового контейнера
    "📅 Сегодня",
    "🚚 Ещё в пути",
    "✏️ Ввести дату вручную",
    "⏭ Пропустить",
    # Раздел «Отчёты»
    "🟢 Активные контейнеры",
    "📋 Активные + вывезенные",
    "🔴 Только вывезенные",
    "🌐 По всем компаниям",
    "🏢 По одной компании",
})


def containers_menu_reply_kb() -> ReplyKeyboardMarkup:
    """Главный экран раздела «Контейнеры»: две кнопки.

    Других кнопок нет — выход в главное меню идёт через persistent-
    клавиатуру Telegram. Текстовый ввод номера контейнера обрабатывается
    напрямую, без необходимости нажимать «➕ Добавить контейнер».
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD_CONTAINER)],
            [KeyboardButton(text=BTN_SEARCH_BY_TYPE)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def containers_type_select_reply_kb() -> ReplyKeyboardMarkup:
    """Клавиатура экрана выбора типа: 5 типов (3+2) и «◀ Назад» в раздел.

    Та же клавиатура остаётся и после клика по типу — для быстрого
    переключения. «Назад» возвращает на главный экран раздела
    (containers_menu), а не в главное меню бота.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="20GP"),
                KeyboardButton(text="20HQ"),
                KeyboardButton(text="40GP"),
            ],
            [
                KeyboardButton(text="40HQ"),
                KeyboardButton(text="45HQ"),
            ],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def container_card_reply_kb(status: str) -> ReplyKeyboardMarkup:
    """Клавиатура действий в карточке контейнера (зависит от статуса)."""
    if status == "on_terminal":
        rows = [
            [KeyboardButton(text=BTN_DEPART)],
            [KeyboardButton(text=BTN_CHANGE_NUMBER)],
            [KeyboardButton(text=BTN_CHANGE_TYPE)],
            [KeyboardButton(text=BTN_CHANGE_COMPANY)],
            [KeyboardButton(text=BTN_DELETE)],
            [KeyboardButton(text=BTN_CARD_BACK_ACTIVE)],
        ]
    elif status == "in_transit":
        rows = [
            [KeyboardButton(text=BTN_ARRIVED)],
            [KeyboardButton(text=BTN_CHANGE_COMPANY)],
            [KeyboardButton(text=BTN_DELETE)],
            [KeyboardButton(text=BTN_CARD_BACK_ACTIVE)],
        ]
    else:  # departed
        # После удаления экрана «Вывезенные» возврат из карточки идёт
        # на главный экран раздела (тот же BTN_CARD_BACK_ACTIVE).
        rows = [
            [KeyboardButton(text=BTN_UNDEPART)],
            [KeyboardButton(text=BTN_EDIT_DEPARTURE_DATE)],
            [KeyboardButton(text=BTN_DELETE)],
            [KeyboardButton(text=BTN_CARD_BACK_ACTIVE)],
        ]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def depart_date_select_reply_kb() -> ReplyKeyboardMarkup:
    """Клавиатура выбора даты вывоза: сегодня / вручную / отмена."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_DEPART_TODAY)],
            [KeyboardButton(text=BTN_DEPART_MANUAL)],
            [KeyboardButton(text=BTN_DEPART_CANCEL)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def depart_manual_date_reply_kb() -> ReplyKeyboardMarkup:
    """Клавиатура подсостояния ручного ввода даты вывоза."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_DEPART_CANCEL)]],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def type_select_reply_kb() -> ReplyKeyboardMarkup:
    """Выбор типа контейнера."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="20GP"),
                KeyboardButton(text="20HQ"),
                KeyboardButton(text="40GP"),
            ],
            [KeyboardButton(text="40HQ"), KeyboardButton(text="45HQ")],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def company_select_reply_kb(companies: list) -> ReplyKeyboardMarkup:
    """Выбор компании для контейнера (по одной в ряд, сортировка по алфавиту)."""
    sorted_companies = sorted(companies, key=lambda c: c["name"].lower())
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=f"🏢 {c['name']}")] for c in sorted_companies
    ]
    rows.append([KeyboardButton(text=BTN_CANCEL)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def delete_confirm_reply_kb() -> ReplyKeyboardMarkup:
    """Подтверждение удаления."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONFIRM_DELETE)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


