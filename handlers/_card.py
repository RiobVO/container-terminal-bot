"""Карточка контейнера — общий код для handlers/containers.py и
handlers/register.py.

Вынесена в отдельный модуль, чтобы разорвать цикл импортов:
containers ↔ register раньше импортировали друг друга внутри функций.
"""
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from db.settings import get_all_settings
from db.users import get_role
from keyboards.containers import container_card_reply_kb
from services.calculator import calculate_container_cost
from services.formatters import fmt_dt, mark, period_label
from states import ContainerSection


def card_text(container, cost: dict, show_tariff: bool = True) -> str:
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
        entry_mark = mark(cost["entry_is_custom"])
        free_mark = mark(cost["free_days_is_custom"])
        rate_mark = mark(cost["storage_rate_is_custom"])
        period_mark = mark(cost["storage_period_is_custom"])
        label = period_label(cost["period_days"])

        tariff_block = (
            f"💰 Стоимость входа: {cost['entry_fee']} $ ({entry_mark})\n"
            f"🆓 Бесплатных дней: {cost['free_days']} ({free_mark})\n"
            f"💵 Ставка хранения: {cost['storage_rate']} $ "
            f"за {cost['period_days']} дн. ({rate_mark}, {label}, {period_mark})"
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
        dep_date = fmt_dt(container["departure_date"])
        arr_date = fmt_dt(container["arrival_date"])
        return (
            f"🔴 <b>Контейнер {display}</b> (Вывезен)\n\n"
            f"🏢 Компания: {company_name}\n"
            f"📦 Тип: {ctype}\n"
            f"📅 Дата прибытия: {arr_date}\n"
            f"📅 Дата вывоза: {dep_date}"
            f"{tariff_section}"
        )

    arr_date = fmt_dt(container["arrival_date"])
    return (
        f"📦 <b>Контейнер {display}</b>\n\n"
        f"🏢 Компания: {company_name}\n"
        f"📦 Тип: {ctype}\n"
        f"📅 Дата прибытия: {arr_date}"
        f"{tariff_section}"
    )


async def send_container_card(
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
        db_role = await get_role(message.from_user.id)
        if db_role:
            actual_role = db_role

    show_tariff = actual_role != "operator"
    await message.answer(
        card_text(container, cost, show_tariff=show_tariff),
        reply_markup=container_card_reply_kb(
            container["status"], with_history=actual_role == "full"
        ),
    )
