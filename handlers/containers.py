"""Хэндлеры раздела контейнеров: главное меню, поиск по типу, карточка.

Двухуровневый вход:
1. Главный экран (ContainerSection.menu) — сводка + 2 кнопки:
   «➕ Добавить контейнер» (показывает подсказку, ввод обрабатывается
   обычным текстовым фолбэком этого же состояния) и «🔍 Найти по типу»
   (переход в search_by_type). Текстовый ввод номера работает напрямую.
2. Поиск по типу (ContainerSection.search_by_type) — клавиатура с пятью
   типами и «◀ Назад» (на главный экран раздела, не в главное меню
   бота). Клик по типу показывает список активных контейнеров этого
   типа, сгруппированный по компаниям, с счётчиком «Общее: N шт» под
   каждой. На обоих подэкранах текстовый ввод номера тоже работает.
"""
import logging
from collections import defaultdict
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from db import companies as db_comp
from db import containers as db_cont
from db.settings import get_all_settings
from keyboards.containers import (
    BTN_ADD_CONTAINER,
    BTN_ARRIVED,
    BTN_CANCEL,
    BTN_CARD_BACK_ACTIVE,
    BTN_CHANGE_COMPANY,
    BTN_CHANGE_NUMBER,
    BTN_CHANGE_TYPE,
    BTN_CONFIRM_DELETE,
    BTN_DELETE,
    BTN_DEPART,
    BTN_DEPART_CANCEL,
    BTN_DEPART_MANUAL,
    BTN_DEPART_TODAY,
    BTN_EDIT_DEPARTURE_DATE,
    BTN_SEARCH_BY_TYPE,
    BTN_UNDEPART,
    CONTAINER_TYPES,
    RESERVED_BUTTON_TEXTS,
    company_select_reply_kb,
    container_card_reply_kb,
    containers_menu_reply_kb,
    containers_type_select_reply_kb,
    delete_confirm_reply_kb,
    depart_date_select_reply_kb,
    depart_manual_date_reply_kb,
    type_select_reply_kb,
)
from keyboards.main import BTN_BACK, BTN_CONTAINERS, main_menu
from services.calculator import calculate_container_cost
from services.normalizer import normalize_container_number
from states import ContainerDepart, ContainerSection, EditContainerNumber

logger = logging.getLogger(__name__)
router = Router()


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------


def _fmt_dt(val: str | None) -> str:
    if not val:
        return "—"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            continue
    return val


def _parse_arrival(val: str | None) -> datetime | None:
    """Парсит arrival_date из строки БД в datetime (или None)."""
    if not val:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _period_label(period_days: int) -> str:
    """Человеческое описание периода начисления."""
    if period_days <= 1:
        return "ежедневный тариф"
    if period_days == 30:
        return "ежемесячный тариф"
    return f"каждые {period_days} дн."


def _mark(is_custom: bool) -> str:
    return "индивидуальный" if is_custom else "стандартный"


def _card_text(container, cost: dict, show_tariff: bool = True) -> str:
    """Формирует текст карточки контейнера.

    show_tariff=False скрывает блок тарификации (для роли operator).
    """
    status = container["status"]
    display = container["display_number"]
    company_name = container["company_name"] or "—"
    ctype = container["type"] or "не указан"

    if status == "in_transit":
        return (
            f"🚚 <b>Контейнер {display}</b> (В пути)\n\n"
            f"🏢 Компания: {company_name}\n"
            f"📦 Тип: {ctype}\n"
            f"⏳ Контейнер ещё не прибыл на терминал."
        )

    tariff_section = ""
    if show_tariff:
        entry_mark = _mark(cost["entry_is_custom"])
        free_mark = _mark(cost["free_days_is_custom"])
        rate_mark = _mark(cost["storage_rate_is_custom"])
        period_mark = _mark(cost["storage_period_is_custom"])
        period_label = _period_label(cost["period_days"])

        tariff_block = (
            f"💰 Стоимость входа: {cost['entry_fee']} $ ({entry_mark})\n"
            f"🆓 Бесплатных дней: {cost['free_days']} ({free_mark})\n"
            f"💵 Ставка хранения: {cost['storage_rate']} $ "
            f"за {cost['period_days']} дн. ({rate_mark}, {period_label}, {period_mark})"
        )

        calc_block = (
            f"📊 <b>Расчёт:</b>\n"
            f"• Дней на терминале: {cost['days']}\n"
            f"• Платных дней: {cost['billable_days']}\n"
            f"• Периодов к оплате: {cost['periods']}\n"
            f"• Вход: {cost['entry']} $\n"
            f"• Хранение: {cost['storage']} $\n"
            f"💰 К оплате: {cost['total']} $"
        )
        tariff_section = f"\n\n💳 <b>Тарификация</b>\n{tariff_block}\n\n{calc_block}"

    if status == "departed":
        dep_date = _fmt_dt(container["departure_date"])
        arr_date = _fmt_dt(container["arrival_date"])
        return (
            f"🔴 <b>Контейнер {display}</b> (Вывезен)\n\n"
            f"🏢 Компания: {company_name}\n"
            f"📦 Тип: {ctype}\n"
            f"📅 Дата прибытия: {arr_date}\n"
            f"📅 Дата вывоза: {dep_date}"
            f"{tariff_section}"
        )

    arr_date = _fmt_dt(container["arrival_date"])
    return (
        f"📦 <b>Контейнер {display}</b>\n\n"
        f"🏢 Компания: {company_name}\n"
        f"📦 Тип: {ctype}\n"
        f"📅 Дата прибытия: {arr_date}"
        f"{tariff_section}"
    )


async def _send_container_card(
    message: Message,
    container,
    state: FSMContext | None = None,
    source: str | None = None,
    role: str = "full",
) -> None:
    """Отправляет карточку контейнера.

    Если передан `state` — переводит FSM в `ContainerSection.card` и пишет
    `container_id` / `card_source`. Если `state=None` (например, при вызове
    из FSM регистрации, где состояние уже сброшено), карточка просто
    отправляется без изменения FSM.

    `source` — откуда открыта карточка: "active" или "departed". Если None
    и state задан, значение берётся из текущих данных FSM (по умолчанию
    "active").

    `role` — роль пользователя. operator не видит блок тарификации.
    """
    settings = await get_all_settings()
    cost = calculate_container_cost(
        container,
        settings,
        comp_entry_fee=container["comp_entry_fee"],
        comp_free_days=container["comp_free_days"],
        comp_storage_rate=container["comp_storage_rate"],
        comp_storage_period_days=container["comp_storage_period_days"],
    )

    if state is not None:
        if source is None:
            data = await state.get_data()
            source = data.get("card_source", "active")
        await state.set_state(ContainerSection.card)
        await state.update_data(
            container_id=container["id"], card_source=source
        )

    # Определяем роль: если не передана явно — берём из БД
    actual_role = role
    if actual_role == "full" and message.from_user:
        from db.users import get_role
        db_role = await get_role(message.from_user.id)
        if db_role:
            actual_role = db_role

    show_tariff = actual_role != "operator"
    await message.answer(
        _card_text(container, cost, show_tariff=show_tariff),
        reply_markup=container_card_reply_kb(container["status"]),
    )


async def _show_menu(message: Message, state: FSMContext) -> None:
    """Главный экран раздела: сводка по статусам + 2 кнопки.

    Кнопки — подсказки. Текстовый ввод номера работает напрямую,
    обходя «➕ Добавить контейнер»: клиент явно об этом просил.
    """
    counts = await db_cont.count_by_status()
    total = sum(counts.values())

    await state.set_state(ContainerSection.menu)

    text = (
        "📦 <b>Раздел контейнеров</b>\n\n"
        f"Всего: {total} | 🚚 В пути: {counts['in_transit']} | "
        f"🟢 На терминале: {counts['on_terminal']} | "
        f"🔴 Вывезенные: {counts['departed']}\n\n"
        "Введите номер контейнера для поиска или регистрации, "
        "либо выберите действие ниже."
    )
    await message.answer(text, reply_markup=containers_menu_reply_kb())


async def _show_type_select(message: Message, state: FSMContext) -> None:
    """Экран выбора типа: клавиатура из 5 типов и «◀ Назад» в menu."""
    await state.set_state(ContainerSection.search_by_type)
    await message.answer(
        "🔍 Выберите тип контейнера для поиска:",
        reply_markup=containers_type_select_reply_kb(),
    )


async def _show_containers_by_type(
    message: Message, state: FSMContext, ctype: str
) -> None:
    """Список активных контейнеров заданного типа, сгруппированный по компаниям.

    Под каждой компанией — строка «Общее: N шт». Сортировка строк внутри
    компании: arrival_date asc, при равенстве — display_number. Сами
    компании — по алфавиту регистронезависимо. После показа FSM остаётся
    в search_by_type, чтобы юзер мог сразу переключиться на другой тип
    или вернуться через ◀ Назад.
    """
    rows = await db_cont.active_by_type(ctype)

    await state.set_state(ContainerSection.search_by_type)

    if not rows:
        await message.answer(
            f"📦 <b>Активные контейнеры типа {ctype}</b>\n\n"
            "Нет активных контейнеров этого типа.",
            reply_markup=containers_type_select_reply_kb(),
        )
        return

    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        cname = r["company_name"] or "—"
        groups[cname].append(r)

    def _row_key(row):
        dt = _parse_arrival(row["arrival_date"]) or datetime.max
        return (dt, (row["display_number"] or ""))

    blocks: list[str] = []
    for cname in sorted(groups.keys(), key=str.lower):
        items = sorted(groups[cname], key=_row_key)
        lines = [f"<b>{cname}:</b>"]
        for r in items:
            lines.append(r["display_number"])
        lines.append(f"<i>Общее: {len(items)} шт</i>")
        blocks.append("\n".join(lines))

    header = (
        f"📦 <b>Активные контейнеры типа {ctype}</b>\n\n"
        f"Всего: {len(rows)}\n\n"
    )
    await message.answer(
        header + "\n\n".join(blocks),
        reply_markup=containers_type_select_reply_kb(),
    )


# ---------------------------------------------------------------------------
# Вход в раздел
# ---------------------------------------------------------------------------


@router.message(F.text == BTN_CONTAINERS)
async def containers_section_enter(
    message: Message, state: FSMContext, role: str
) -> None:
    """Вход в раздел контейнеров."""
    if role not in ("full", "operator"):
        await message.answer("⛔ У вас нет доступа. Обратитесь к администратору.")
        return
    await state.update_data(user_role=role)
    await _show_menu(message, state)


async def _process_number_text(
    message: Message, state: FSMContext, text: str
) -> None:
    """Общая обработка текстового ввода номера контейнера.

    Используется на главном экране и на экране выбора типа: пытается
    нормализовать текст как номер. Существующий номер открывает карточку
    (любого статуса), новый — запускает FSM регистрации, невалидный
    формат даёт ошибку с примером.
    """
    result = normalize_container_number(text)
    if result is None:
        await message.answer(
            "❌ Неверный формат номера. Пример: <b>CASS 1234567</b>"
        )
        return

    normalized, display = result
    existing = await db_cont.find_by_number(normalized)

    if existing:
        source = "departed" if existing["status"] == "departed" else "active"
        await _send_container_card(message, existing, state, source=source)
        return

    from handlers.register import start_registration
    await start_registration(message, state, normalized, display)


# ---------------------------------------------------------------------------
# Состояние: главный экран раздела
# ---------------------------------------------------------------------------


@router.message(ContainerSection.menu, F.text == BTN_ADD_CONTAINER)
async def menu_add_container(message: Message, state: FSMContext) -> None:
    """Кнопка-подсказка: следующее текстовое сообщение трактуем как номер.

    FSM остаётся в menu — обычный фолбэк состояния как раз обработает
    введённый номер. Если такой номер уже есть в базе, фолбэк откроет
    его карточку, а не запустит регистрацию (валидное поведение).
    """
    await message.answer(
        "Введите номер нового контейнера (например: <b>CASS 1234567</b>):"
    )


@router.message(ContainerSection.menu, F.text == BTN_SEARCH_BY_TYPE)
async def menu_search_by_type(message: Message, state: FSMContext) -> None:
    await _show_type_select(message, state)


@router.message(ContainerSection.menu)
async def menu_text_input(
    message: Message, state: FSMContext, role: str
) -> None:
    """Текстовый ввод на главном экране → поиск/регистрация контейнера."""
    if role not in ("full", "operator"):
        return
    text = (message.text or "").strip()
    if not text or text in RESERVED_BUTTON_TEXTS:
        return
    await _process_number_text(message, state, text)


# ---------------------------------------------------------------------------
# Состояние: поиск по типу (выбор типа + список найденных)
# ---------------------------------------------------------------------------


@router.message(ContainerSection.search_by_type, F.text == BTN_BACK)
async def search_back_to_menu(
    message: Message, state: FSMContext
) -> None:
    """«◀ Назад» возвращает на главный экран раздела, а не в главное меню."""
    await _show_menu(message, state)


@router.message(
    ContainerSection.search_by_type, F.text.in_(CONTAINER_TYPES)
)
async def search_type_selected(
    message: Message, state: FSMContext
) -> None:
    await _show_containers_by_type(message, state, message.text)


@router.message(ContainerSection.search_by_type)
async def search_text_input(
    message: Message, state: FSMContext, role: str
) -> None:
    """На экране выбора типа тоже разрешён ручной ввод номера."""
    if role not in ("full", "operator"):
        return
    text = (message.text or "").strip()
    if not text or text in RESERVED_BUTTON_TEXTS:
        return
    await _process_number_text(message, state, text)


# ---------------------------------------------------------------------------
# Состояние: карточка
# ---------------------------------------------------------------------------


async def _reload_and_send_card(message: Message, state: FSMContext) -> None:
    """Перезагружает контейнер из БД и отправляет карточку заново."""
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return
    container = await db_cont.get_container(container_id)
    if container is None:
        await message.answer("⚠️ Контейнер не найден.")
        await _show_menu(message, state)
        return
    await _send_container_card(message, container, state)


@router.message(ContainerSection.card, F.text == BTN_CARD_BACK_ACTIVE)
async def card_back_to_active(message: Message, state: FSMContext) -> None:
    await _show_menu(message, state)


@router.message(ContainerSection.card, F.text == BTN_ARRIVED)
async def card_arrived(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return
    await db_cont.set_arrived(container_id)
    await message.answer("✅ Контейнер прибыл на терминал")
    await _reload_and_send_card(message, state)


@router.message(ContainerSection.card, F.text == BTN_DEPART)
async def card_depart_start(message: Message, state: FSMContext) -> None:
    """Запускает FSM выбора даты вывоза вместо моментального вывоза."""
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return
    container = await db_cont.get_container(container_id)
    if not container:
        return

    await state.set_state(ContainerDepart.waiting_for_departure_date)
    await state.update_data(container_id=container_id, depart_mode="depart")

    await message.answer(
        f"📤 Вывоз контейнера <b>{container['display_number']}</b>\n\n"
        "Когда контейнер был вывезен с терминала?"
    )
    await message.answer(
        "Выберите дату:",
        reply_markup=depart_date_select_reply_kb(),
    )


@router.message(ContainerSection.card, F.text == BTN_EDIT_DEPARTURE_DATE)
async def card_edit_departure_date(
    message: Message, state: FSMContext
) -> None:
    """Запускает FSM редактирования даты вывоза для уже вывезенного."""
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return
    container = await db_cont.get_container(container_id)
    if not container:
        return

    cur = _parse_arrival(container["departure_date"])
    cur_text = cur.strftime("%d.%m.%Y") if cur else "—"

    await state.set_state(ContainerDepart.waiting_for_departure_date)
    await state.update_data(container_id=container_id, depart_mode="edit")

    await message.answer(
        f"📅 Изменение даты вывоза контейнера "
        f"<b>{container['display_number']}</b>\n\n"
        f"Текущая дата вывоза: {cur_text}"
    )
    await message.answer(
        "Выберите дату:",
        reply_markup=depart_date_select_reply_kb(),
    )


@router.message(ContainerSection.card, F.text == BTN_UNDEPART)
async def card_undepart(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return
    await db_cont.undo_departure(container_id)
    await state.update_data(card_source="active")
    await message.answer("✅ Вывоз отменён")
    await _reload_and_send_card(message, state)


@router.message(ContainerSection.card, F.text == BTN_CHANGE_NUMBER)
async def card_change_number(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return
    container = await db_cont.get_container(container_id)
    if not container:
        return
    await state.set_state(EditContainerNumber.waiting_for_number)
    await state.update_data(container_id=container_id)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )
    await message.answer(
        f"✏️ Введите новый номер для контейнера "
        f"<b>{container['display_number']}</b>:\n\nПример: <b>CASS 1234567</b>",
        reply_markup=cancel_kb,
    )


@router.message(ContainerSection.card, F.text == BTN_CHANGE_TYPE)
async def card_change_type(message: Message, state: FSMContext) -> None:
    await state.set_state(ContainerSection.choosing_type)
    await message.answer(
        "Выберите тип контейнера:",
        reply_markup=type_select_reply_kb(),
    )


@router.message(ContainerSection.card, F.text == BTN_CHANGE_COMPANY)
async def card_change_company(message: Message, state: FSMContext) -> None:
    companies = await db_comp.list_companies()
    if not companies:
        await message.answer("⚠️ Нет компаний.")
        return
    await state.set_state(ContainerSection.choosing_company)
    await message.answer(
        "🏢 Выберите компанию:",
        reply_markup=company_select_reply_kb(companies),
    )


@router.message(ContainerSection.card, F.text == BTN_DELETE)
async def card_delete_ask(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return
    container = await db_cont.get_container(container_id)
    if not container:
        return
    await state.set_state(ContainerSection.confirming_delete)
    await message.answer(
        f"⚠️ Удалить контейнер <b>{container['display_number']}</b>?",
        reply_markup=delete_confirm_reply_kb(),
    )


@router.message(ContainerSection.card)
async def card_fallback(message: Message) -> None:
    """Любой не-зарезервированный текст в карточке игнорируем."""
    # В состоянии card любой другой текст НЕ валидируем как номер.
    return


# ---------------------------------------------------------------------------
# FSM выбора даты вывоза (новый вывоз и редактирование)
# ---------------------------------------------------------------------------


def _validate_departure(
    departure: datetime, arrival_str: str | None
) -> str | None:
    """Возвращает текст ошибки или None, если дата валидна.

    Сравнение календарными датами (без часов): дата вывоза не должна
    быть в будущем и не должна быть раньше дня прибытия.
    """
    today = datetime.now().date()
    if departure.date() > today:
        return "❌ Дата вывоза не может быть в будущем."
    arrival = _parse_arrival(arrival_str) if arrival_str else None
    if arrival is not None and departure.date() < arrival.date():
        return (
            "❌ Дата вывоза не может быть раньше даты прибытия "
            f"({arrival.strftime('%d.%m.%Y')})."
        )
    return None


async def _restore_card_after_cancel(
    message: Message, state: FSMContext
) -> None:
    """Сбрасывает FSM выбора даты и заново отправляет исходную карточку."""
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        await _show_menu(message, state)
        return
    container = await db_cont.get_container(container_id)
    if container is None:
        await _show_menu(message, state)
        return
    await _send_container_card(message, container, state)


async def _finalize_departure(
    message: Message,
    state: FSMContext,
    departure: datetime,
    *,
    used_today_button: bool,
) -> None:
    """Сохраняет дату вывоза и отправляет обновлённую карточку.

    ``used_today_button`` влияет только на формат подтверждающего
    сообщения для режима ``depart``: при выборе «Сегодня» дату не
    показываем (как в спеке), при ручном вводе — показываем.
    """
    data = await state.get_data()
    container_id = data.get("container_id")
    mode = data.get("depart_mode", "depart")
    if container_id is None:
        return

    container = await db_cont.get_container(container_id)
    if container is None:
        await message.answer("⚠️ Контейнер не найден.")
        await _show_menu(message, state)
        return

    dt_str = departure.strftime("%Y-%m-%d %H:%M:%S")
    display = container["display_number"]
    pretty = departure.strftime("%d.%m.%Y")

    if mode == "edit":
        await db_cont.update_departure_date(container_id, dt_str)
        confirmation = f"✅ Дата вывоза изменена на {pretty}."
    else:
        await db_cont.set_departed(container_id, dt_str)
        confirmation = (
            f"✅ Контейнер {display} вывезен."
            if used_today_button
            else f"✅ Контейнер {display} вывезен {pretty}."
        )

    await message.answer(confirmation)

    # Live-лента: уведомление в группы о вывозе
    if mode != "edit" and hasattr(message.bot, "_group_ids") and message.bot._group_ids:
        from services.group_notify import notify_groups
        fresh_for_notify = await db_cont.get_container(container_id)
        if fresh_for_notify:
            from db.settings import get_all_settings as _get_settings
            _settings = await _get_settings()
            _cost = calculate_container_cost(
                fresh_for_notify, _settings,
                comp_entry_fee=fresh_for_notify["comp_entry_fee"],
                comp_free_days=fresh_for_notify["comp_free_days"],
                comp_storage_rate=fresh_for_notify["comp_storage_rate"],
                comp_storage_period_days=fresh_for_notify["comp_storage_period_days"],
            )
            username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
            notify_text = (
                f"🚛 <b>Вывоз</b>\n"
                f"{fresh_for_notify['display_number']} ({fresh_for_notify['company_name'] or '—'})"
                f" — {fresh_for_notify['type'] or 'тип не указан'}\n"
                f"Дней на терминале: {_cost['days']} | К оплате: {_cost['total']} $\n"
                f"Оператор: {username}"
            )
            await notify_groups(message.bot, message.bot._group_ids, notify_text)

    fresh = await db_cont.get_container(container_id)
    if fresh is not None:
        await _send_container_card(message, fresh, state)


@router.message(
    ContainerDepart.waiting_for_departure_date, F.text == BTN_DEPART_CANCEL
)
async def depart_cancel_select(
    message: Message, state: FSMContext
) -> None:
    await _restore_card_after_cancel(message, state)


@router.message(
    ContainerDepart.waiting_for_departure_date, F.text == BTN_DEPART_TODAY
)
async def depart_today(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return
    container = await db_cont.get_container(container_id)
    if container is None:
        await _show_menu(message, state)
        return

    now = datetime.now()
    err = _validate_departure(now, container["arrival_date"])
    if err is not None:
        await message.answer(err)
        return

    await _finalize_departure(
        message, state, now, used_today_button=True
    )


@router.message(
    ContainerDepart.waiting_for_departure_date, F.text == BTN_DEPART_MANUAL
)
async def depart_choose_manual(
    message: Message, state: FSMContext
) -> None:
    await state.set_state(ContainerDepart.waiting_for_manual_date)
    await message.answer(
        "Введите дату вывоза в формате <b>ДД.ММ.ГГГГ</b>\n"
        "Например: <code>15.03.2026</code>",
        reply_markup=depart_manual_date_reply_kb(),
    )


@router.message(ContainerDepart.waiting_for_departure_date)
async def depart_select_fallback(message: Message) -> None:
    await message.answer("Выберите вариант из кнопок ниже.")


@router.message(
    ContainerDepart.waiting_for_manual_date, F.text == BTN_DEPART_CANCEL
)
async def depart_cancel_manual(
    message: Message, state: FSMContext
) -> None:
    await _restore_card_after_cancel(message, state)


@router.message(ContainerDepart.waiting_for_manual_date)
async def depart_manual_input(
    message: Message, state: FSMContext
) -> None:
    text = (message.text or "").strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Пример: <code>15.03.2026</code>"
        )
        return

    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return
    container = await db_cont.get_container(container_id)
    if container is None:
        await _show_menu(message, state)
        return

    err = _validate_departure(dt, container["arrival_date"])
    if err is not None:
        await message.answer(err)
        return

    await _finalize_departure(
        message, state, dt, used_today_button=False
    )


# ---------------------------------------------------------------------------
# Состояние: выбор типа
# ---------------------------------------------------------------------------


@router.message(ContainerSection.choosing_type, F.text == BTN_CANCEL)
async def type_cancel(message: Message, state: FSMContext) -> None:
    await _reload_and_send_card(message, state)


@router.message(ContainerSection.choosing_type, F.text.in_(CONTAINER_TYPES))
async def type_selected(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return
    await db_cont.update_type(container_id, message.text)
    await _reload_and_send_card(message, state)


@router.message(ContainerSection.choosing_type)
async def type_fallback(message: Message) -> None:
    return


# ---------------------------------------------------------------------------
# Состояние: выбор компании (смена)
# ---------------------------------------------------------------------------


@router.message(ContainerSection.choosing_company, F.text == BTN_CANCEL)
async def company_cancel(message: Message, state: FSMContext) -> None:
    await _reload_and_send_card(message, state)


@router.message(ContainerSection.choosing_company)
async def company_selected(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.startswith("🏢 "):
        return
    name = text[2:].strip()

    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return

    company = await db_comp.get_company_by_name_ci(name)
    if not company:
        await message.answer("⚠️ Компания не найдена, выберите из списка.")
        return

    await db_cont.update_company(container_id, company["id"])
    await _reload_and_send_card(message, state)


# ---------------------------------------------------------------------------
# Состояние: подтверждение удаления
# ---------------------------------------------------------------------------


@router.message(ContainerSection.confirming_delete, F.text == BTN_CANCEL)
async def delete_cancel(message: Message, state: FSMContext) -> None:
    await _reload_and_send_card(message, state)


@router.message(ContainerSection.confirming_delete, F.text == BTN_CONFIRM_DELETE)
async def delete_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return

    # Сохраняем данные для уведомления ДО удаления
    container = await db_cont.get_container(container_id)
    display = container["display_number"] if container else "?"
    company = (container["company_name"] or "—") if container else "—"

    await db_cont.delete_container(container_id)
    await message.answer("✅ Удалено")

    # Live-лента: уведомление в группы
    if hasattr(message.bot, "_group_ids") and message.bot._group_ids:
        from services.group_notify import notify_groups
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        notify_text = (
            f"🗑 <b>Удалён контейнер</b>\n"
            f"{display} ({company})\n"
            f"Оператор: {username}"
        )
        await notify_groups(message.bot, message.bot._group_ids, notify_text)

    await _show_menu(message, state)


@router.message(ContainerSection.confirming_delete)
async def delete_fallback(message: Message) -> None:
    return


# ---------------------------------------------------------------------------
# Состояние: редактирование номера (текстовый ввод)
# ---------------------------------------------------------------------------


@router.message(EditContainerNumber.waiting_for_number, F.text == BTN_CANCEL)
async def edit_number_cancel(message: Message, state: FSMContext) -> None:
    await _reload_and_send_card(message, state)


@router.message(EditContainerNumber.waiting_for_number)
async def edit_number_process(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text in RESERVED_BUTTON_TEXTS:
        # Защита от зарезервированных кнопок.
        return

    result = normalize_container_number(text)
    if result is None:
        await message.answer(
            "❌ Неверный формат номера. Пример: <b>CASS 1234567</b>"
        )
        return

    normalized, display = result
    data = await state.get_data()
    container_id = data["container_id"]

    ok = await db_cont.update_number(container_id, normalized, display)
    if not ok:
        await message.answer("❌ Контейнер с таким номером уже существует.")
        return

    container = await db_cont.get_container(container_id)
    if container:
        await _send_container_card(message, container, state)
