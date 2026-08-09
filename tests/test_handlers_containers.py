"""Тесты handlers/containers.py: меню раздела, поиск по типу, карточка,
смена статусов (прибыл/вывезен), редактирование полей, удаление.

Хендлеры вызываются напрямую с mock-сообщением и настоящим FSMContext.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from db import companies as db_comp
from db import containers as db_cont
from handlers import containers as hc
from services import formatters as fmt
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
)
from keyboards.main import BTN_BACK
from states import (
    ContainerDepart,
    ContainerSection,
    EditContainerNumber,
    RegisterContainer,
)

ARRIVAL = "2026-06-01 10:00:00"


async def _seed_container(
    number: str = "AAAU1111111",
    display: str = "AAAU 1111111",
    status: str = "on_terminal",
    arrival: str | None = ARRIVAL,
    company_id: int | None = None,
    ctype: str | None = "40HQ",
) -> int:
    cid = await db_cont.add_container(
        number=number,
        display_number=display,
        company_id=company_id,
        status=status,
        arrival_date=arrival,
        container_type=ctype,
    )
    return cid


async def _seed_departed(
    number: str = "DDDU4444444",
    display: str = "DDDU 4444444",
    departure: str = "2026-06-05 12:00:00",
) -> int:
    cid = await _seed_container(number=number, display=display)
    await db_cont.set_departed(cid, departure)
    return cid


def _all_texts(msg) -> str:
    return "\n".join(c.args[0] for c in msg.answer.call_args_list)


# ---------------------------------------------------------------------------
# Утилиты форматирования
# ---------------------------------------------------------------------------


def test_fmt_dt_variants():
    """Все ветки fmt_dt: пусто, оба формата, мусор как есть."""
    assert fmt.fmt_dt(None) == "—"
    assert fmt.fmt_dt("") == "—"
    assert fmt.fmt_dt("2026-06-01 10:30:00") == "01.06.2026 10:30"
    assert fmt.fmt_dt("2026-06-01") == "01.06.2026 00:00"
    assert fmt.fmt_dt("garbage") == "garbage"


def test_parse_arrival_variants():
    """Все ветки _parse_arrival: пусто, оба формата, мусор → None."""
    assert hc._parse_arrival(None) is None
    assert hc._parse_arrival("2026-06-01 10:30:00") == datetime(
        2026, 6, 1, 10, 30
    )
    assert hc._parse_arrival("2026-06-01") == datetime(2026, 6, 1)
    assert hc._parse_arrival("garbage") is None


def test_period_label():
    assert fmt.period_label(1) == "ежедневный тариф"
    assert fmt.period_label(30) == "ежемесячный тариф"
    assert fmt.period_label(7) == "каждые 7 дн."


def test_mark():
    assert fmt.mark(True) == "индивидуальный"
    assert fmt.mark(False) == "стандартный"


# ---------------------------------------------------------------------------
# Вход в раздел
# ---------------------------------------------------------------------------


async def test_section_enter_full(test_db, make_message, fsm_state):
    msg = make_message()
    await hc.containers_section_enter(msg, fsm_state, role="full")
    assert await fsm_state.get_state() == ContainerSection.menu.state
    assert "Раздел контейнеров" in msg.answer.call_args[0][0]


async def test_section_enter_counts(test_db, make_message, fsm_state):
    """Сводка показывает количество по каждому статусу."""
    await _seed_container(
        number="AAAU1111111", display="AAAU 1111111", status="in_transit",
        arrival=None,
    )
    await _seed_container(number="BBBU2222222", display="BBBU 2222222")
    await _seed_departed()
    msg = make_message()
    await hc.containers_section_enter(msg, fsm_state, role="full")
    text = msg.answer.call_args[0][0]
    assert "Всего: 3" in text
    assert "В пути: 1" in text
    assert "На терминале: 1" in text
    assert "Вывезенные: 1" in text


async def test_section_enter_no_access(test_db, make_message, fsm_state):
    msg = make_message()
    await hc.containers_section_enter(msg, fsm_state, role="reports_only")
    assert "нет доступа" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() is None


# ---------------------------------------------------------------------------
# Главный экран раздела
# ---------------------------------------------------------------------------


async def test_menu_add_container_hint(test_db, make_message, fsm_state):
    await fsm_state.set_state(ContainerSection.menu)
    msg = make_message(BTN_ADD_CONTAINER)
    await hc.menu_add_container(msg, fsm_state)
    assert "Введите номер" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() == ContainerSection.menu.state


async def test_menu_search_by_type(test_db, make_message, fsm_state):
    await fsm_state.set_state(ContainerSection.menu)
    msg = make_message(BTN_SEARCH_BY_TYPE)
    await hc.menu_search_by_type(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.search_by_type.state
    assert "Выберите тип" in msg.answer.call_args[0][0]


async def test_menu_text_existing_opens_card(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.menu)
    msg = make_message("aaau 1111111")
    await hc.menu_text_input(msg, fsm_state, role="full")
    assert await fsm_state.get_state() == ContainerSection.card.state
    data = await fsm_state.get_data()
    assert data["container_id"] == cid
    assert data["card_source"] == "active"
    assert "AAAU 1111111" in msg.answer.call_args[0][0]


async def test_menu_text_departed_sets_source(test_db, make_message, fsm_state):
    cid = await _seed_departed()
    await fsm_state.set_state(ContainerSection.menu)
    msg = make_message("DDDU 4444444")
    await hc.menu_text_input(msg, fsm_state, role="full")
    data = await fsm_state.get_data()
    assert data["container_id"] == cid
    assert data["card_source"] == "departed"
    text = msg.answer.call_args[0][0]
    assert "Вывезен" in text
    assert "Дата вывоза" in text


async def test_menu_text_new_starts_registration(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(ContainerSection.menu)
    msg = make_message("HLXU 7777777")
    await hc.menu_text_input(msg, fsm_state, role="full")
    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_company.state
    )


async def test_menu_text_invalid_number(test_db, make_message, fsm_state):
    await fsm_state.set_state(ContainerSection.menu)
    msg = make_message("not-a-number")
    await hc.menu_text_input(msg, fsm_state, role="full")
    assert "Неверный формат" in msg.answer.call_args[0][0]


async def test_menu_text_reserved_ignored(test_db, make_message, fsm_state):
    msg = make_message(BTN_CANCEL)
    await hc.menu_text_input(msg, fsm_state, role="full")
    msg.answer.assert_not_called()


async def test_menu_text_empty_ignored(test_db, make_message, fsm_state):
    msg = make_message("   ")
    await hc.menu_text_input(msg, fsm_state, role="full")
    msg.answer.assert_not_called()


async def test_menu_text_no_access_ignored(test_db, make_message, fsm_state):
    msg = make_message("HLXU 7777777")
    await hc.menu_text_input(msg, fsm_state, role="reports_only")
    msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Карточка: содержимое по статусам и ролям
# ---------------------------------------------------------------------------


async def test_card_in_transit_text(test_db, make_message, fsm_state):
    await _seed_container(status="in_transit", arrival=None)
    msg = make_message("AAAU 1111111")
    await hc.menu_text_input(msg, fsm_state, role="full")
    text = msg.answer.call_args[0][0]
    assert "В пути" in text
    assert "ещё не прибыл" in text
    assert "Тарификация" not in text


async def test_card_on_terminal_shows_tariff(test_db, make_message, fsm_state):
    """full видит блок тарификации с индивидуальными параметрами компании."""
    company_id = await db_comp.add_company(
        name="Ромашка", entry_fee=50.0, free_days=10
    )
    await _seed_container(company_id=company_id)
    msg = make_message("AAAU 1111111")
    await hc.menu_text_input(msg, fsm_state, role="full")
    text = msg.answer.call_args[0][0]
    assert "Тарификация" in text
    assert "индивидуальный" in text
    assert "стандартный" in text
    assert "Ромашка" in text


async def test_card_operator_hides_tariff(test_db, make_message, fsm_state):
    """operator не видит тарифы (строка ~216: show_tariff=False)."""
    await _seed_container()
    msg = make_message("AAAU 1111111")
    await hc.menu_text_input(msg, fsm_state, role="operator")
    text = msg.answer.call_args[0][0]
    assert "Тарификация" not in text
    assert "К оплате" not in text


async def test_card_role_from_db_when_unknown_user(
    test_db, make_message, fsm_state
):
    """Юзер без записи в users: get_role вернул None, роль остаётся full."""
    await _seed_container()
    msg = make_message("AAAU 1111111")
    msg.from_user.id = 999999  # нет в таблице users
    await hc.menu_text_input(msg, fsm_state, role="full")
    assert "Тарификация" in msg.answer.call_args[0][0]


async def test_card_no_type_and_no_company(test_db, make_message, fsm_state):
    """Фолбэки «—» для компании и «не указан» для типа."""
    await _seed_container(ctype=None)
    msg = make_message("AAAU 1111111")
    await hc.menu_text_input(msg, fsm_state, role="full")
    text = msg.answer.call_args[0][0]
    assert "Компания: —" in text
    assert "не указан" in text


# ---------------------------------------------------------------------------
# Поиск по типу
# ---------------------------------------------------------------------------


async def test_search_back_to_menu(test_db, make_message, fsm_state):
    await fsm_state.set_state(ContainerSection.search_by_type)
    msg = make_message(BTN_BACK)
    await hc.search_back_to_menu(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.menu.state


async def test_search_type_empty_list(test_db, make_message, fsm_state):
    await fsm_state.set_state(ContainerSection.search_by_type)
    msg = make_message("40HQ")
    await hc.search_type_selected(msg, fsm_state)
    assert "Нет активных контейнеров" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() == ContainerSection.search_by_type.state


async def test_search_type_grouped_list(test_db, make_message, fsm_state):
    """Группировка по компаниям, «—» для пустой, сортировка по дате."""
    comp_a = await db_comp.add_company(name="Astra")
    comp_b = await db_comp.add_company(name="berry")
    await _seed_container(
        number="AAAU1111111", display="AAAU 1111111",
        company_id=comp_a, arrival="2026-06-02 10:00:00",
    )
    await _seed_container(
        number="BBBU2222222", display="BBBU 2222222",
        company_id=comp_a, arrival="2026-06-01 10:00:00",
    )
    await _seed_container(
        number="CCCU3333333", display="CCCU 3333333", company_id=comp_b
    )
    # Без компании и без даты прибытия — ветки «—» и datetime.max
    await _seed_container(
        number="EEEU5555555", display="EEEU 5555555", arrival=None
    )
    # Не того типа — не попадает в выдачу
    await _seed_container(
        number="FFFU6666666", display="FFFU 6666666", ctype="20GP"
    )
    msg = make_message("40HQ")
    await hc.search_type_selected(msg, fsm_state)
    text = msg.answer.call_args[0][0]
    assert "Всего: 4" in text
    assert "Общее: 2 шт" in text
    # Внутри Astra сортировка по arrival_date asc
    assert text.index("BBBU 2222222") < text.index("AAAU 1111111")
    # Компании по алфавиту регистронезависимо, «—» последняя
    assert text.index("Astra") < text.index("berry")
    assert "—" in text
    assert "FFFU 6666666" not in text


async def test_search_text_existing_opens_card(
    test_db, make_message, fsm_state
):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.search_by_type)
    msg = make_message("AAAU 1111111")
    await hc.search_text_input(msg, fsm_state, role="full")
    assert await fsm_state.get_state() == ContainerSection.card.state
    assert (await fsm_state.get_data())["container_id"] == cid


async def test_search_text_reserved_and_empty(test_db, make_message, fsm_state):
    msg = make_message(BTN_BACK)
    await hc.search_text_input(msg, fsm_state, role="full")
    msg.answer.assert_not_called()
    msg2 = make_message("")
    await hc.search_text_input(msg2, fsm_state, role="full")
    msg2.answer.assert_not_called()


async def test_search_text_no_access(test_db, make_message, fsm_state):
    msg = make_message("AAAU 1111111")
    await hc.search_text_input(msg, fsm_state, role="none")
    msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Карточка: навигация и перезагрузка
# ---------------------------------------------------------------------------


async def test_card_back_to_active(test_db, make_message, fsm_state):
    await fsm_state.set_state(ContainerSection.card)
    msg = make_message(BTN_CARD_BACK_ACTIVE)
    await hc.card_back_to_active(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.menu.state


async def test_reload_card_no_id(test_db, make_message, fsm_state):
    """_reload_and_send_card без container_id молча выходит."""
    msg = make_message(BTN_CANCEL)
    await hc.type_cancel(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_reload_card_missing_container(test_db, make_message, fsm_state):
    """Контейнер удалён из БД: предупреждение и возврат в меню."""
    await fsm_state.set_data({"container_id": 999})
    msg = make_message(BTN_CANCEL)
    await hc.type_cancel(msg, fsm_state)
    assert "не найден" in msg.answer.call_args_list[0].args[0]
    assert await fsm_state.get_state() == ContainerSection.menu.state


# ---------------------------------------------------------------------------
# Карточка: прибытие
# ---------------------------------------------------------------------------


async def test_card_arrived(test_db, make_message, fsm_state):
    cid = await _seed_container(status="in_transit", arrival=None)
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message(BTN_ARRIVED)
    await hc.card_arrived(msg, fsm_state)
    fresh = await db_cont.get_container(cid)
    assert fresh["status"] == "on_terminal"
    assert fresh["arrival_date"] is not None
    assert "прибыл" in msg.answer.call_args_list[0].args[0]


async def test_card_arrived_no_id(test_db, make_message, fsm_state):
    msg = make_message(BTN_ARRIVED)
    await hc.card_arrived(msg, fsm_state)
    msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Карточка: запуск вывоза и редактирования даты
# ---------------------------------------------------------------------------


async def test_card_depart_start(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message(BTN_DEPART)
    await hc.card_depart_start(msg, fsm_state)
    assert (
        await fsm_state.get_state()
        == ContainerDepart.waiting_for_departure_date.state
    )
    data = await fsm_state.get_data()
    assert data["depart_mode"] == "depart"
    assert "Вывоз контейнера" in msg.answer.call_args_list[0].args[0]


async def test_card_depart_start_no_id(test_db, make_message, fsm_state):
    msg = make_message(BTN_DEPART)
    await hc.card_depart_start(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_card_depart_start_missing_container(
    test_db, make_message, fsm_state
):
    await fsm_state.set_data({"container_id": 999})
    msg = make_message(BTN_DEPART)
    await hc.card_depart_start(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_card_edit_departure_date(test_db, make_message, fsm_state):
    cid = await _seed_departed()
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": cid, "card_source": "departed"})
    msg = make_message(BTN_EDIT_DEPARTURE_DATE)
    await hc.card_edit_departure_date(msg, fsm_state)
    assert (
        await fsm_state.get_state()
        == ContainerDepart.waiting_for_departure_date.state
    )
    assert (await fsm_state.get_data())["depart_mode"] == "edit"
    assert "05.06.2026" in msg.answer.call_args_list[0].args[0]


async def test_card_edit_departure_date_empty(test_db, make_message, fsm_state):
    """Дата вывоза отсутствует — показываем «—»."""
    cid = await _seed_container()
    await fsm_state.set_data({"container_id": cid})
    msg = make_message(BTN_EDIT_DEPARTURE_DATE)
    await hc.card_edit_departure_date(msg, fsm_state)
    assert "Текущая дата вывоза: —" in msg.answer.call_args_list[0].args[0]


async def test_card_edit_departure_no_id(test_db, make_message, fsm_state):
    msg = make_message(BTN_EDIT_DEPARTURE_DATE)
    await hc.card_edit_departure_date(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_card_edit_departure_missing_container(
    test_db, make_message, fsm_state
):
    await fsm_state.set_data({"container_id": 999})
    msg = make_message(BTN_EDIT_DEPARTURE_DATE)
    await hc.card_edit_departure_date(msg, fsm_state)
    msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Карточка: отмена вывоза
# ---------------------------------------------------------------------------


async def test_card_undepart(test_db, make_message, fsm_state):
    cid = await _seed_departed()
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": cid, "card_source": "departed"})
    msg = make_message(BTN_UNDEPART)
    await hc.card_undepart(msg, fsm_state)
    fresh = await db_cont.get_container(cid)
    assert fresh["status"] == "on_terminal"
    assert fresh["departure_date"] is None
    assert (await fsm_state.get_data())["card_source"] == "active"
    assert "Вывоз отменён" in msg.answer.call_args_list[0].args[0]


async def test_card_undepart_no_id(test_db, make_message, fsm_state):
    msg = make_message(BTN_UNDEPART)
    await hc.card_undepart(msg, fsm_state)
    msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Карточка: изменение номера
# ---------------------------------------------------------------------------


async def test_card_change_number(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": cid})
    msg = make_message(BTN_CHANGE_NUMBER)
    await hc.card_change_number(msg, fsm_state)
    assert (
        await fsm_state.get_state()
        == EditContainerNumber.waiting_for_number.state
    )
    assert "новый номер" in msg.answer.call_args[0][0]


async def test_card_change_number_no_id(test_db, make_message, fsm_state):
    msg = make_message(BTN_CHANGE_NUMBER)
    await hc.card_change_number(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_card_change_number_missing_container(
    test_db, make_message, fsm_state
):
    await fsm_state.set_data({"container_id": 999})
    msg = make_message(BTN_CHANGE_NUMBER)
    await hc.card_change_number(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_edit_number_cancel(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(EditContainerNumber.waiting_for_number)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message(BTN_CANCEL)
    await hc.edit_number_cancel(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.card.state


async def test_edit_number_reserved_ignored(test_db, make_message, fsm_state):
    msg = make_message(BTN_DEPART)
    await hc.edit_number_process(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_edit_number_invalid(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_data({"container_id": cid})
    msg = make_message("BAD123")
    await hc.edit_number_process(msg, fsm_state)
    assert "Неверный формат" in msg.answer.call_args[0][0]


async def test_edit_number_duplicate(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await _seed_container(number="BBBU2222222", display="BBBU 2222222")
    await fsm_state.set_data({"container_id": cid})
    msg = make_message("BBBU 2222222")
    await hc.edit_number_process(msg, fsm_state)
    assert "уже существует" in msg.answer.call_args[0][0]


async def test_edit_number_success(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message("ZZZU 9999999")
    await hc.edit_number_process(msg, fsm_state)
    fresh = await db_cont.get_container(cid)
    assert fresh["number"] == "ZZZU9999999"
    assert "ZZZU 9999999" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() == ContainerSection.card.state


# ---------------------------------------------------------------------------
# Карточка: изменение типа
# ---------------------------------------------------------------------------


async def test_card_change_type(test_db, make_message, fsm_state):
    await fsm_state.set_state(ContainerSection.card)
    msg = make_message(BTN_CHANGE_TYPE)
    await hc.card_change_type(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.choosing_type.state


async def test_type_selected(test_db, make_message, fsm_state):
    cid = await _seed_container(ctype="20GP")
    await fsm_state.set_state(ContainerSection.choosing_type)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message("45HQ")
    await hc.type_selected(msg, fsm_state)
    fresh = await db_cont.get_container(cid)
    assert fresh["type"] == "45HQ"
    assert await fsm_state.get_state() == ContainerSection.card.state


async def test_type_selected_no_id(test_db, make_message, fsm_state):
    msg = make_message("45HQ")
    await hc.type_selected(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_type_cancel_restores_card(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.choosing_type)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message(BTN_CANCEL)
    await hc.type_cancel(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.card.state


async def test_type_fallback_silent(test_db, make_message, fsm_state):
    msg = make_message("что-то")
    await hc.type_fallback(msg)
    msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Карточка: смена компании
# ---------------------------------------------------------------------------


async def test_card_change_company_no_companies(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(ContainerSection.card)
    msg = make_message(BTN_CHANGE_COMPANY)
    await hc.card_change_company(msg, fsm_state)
    assert "Нет компаний" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() == ContainerSection.card.state


async def test_card_change_company(test_db, make_message, fsm_state):
    await db_comp.add_company(name="Ромашка")
    await fsm_state.set_state(ContainerSection.card)
    msg = make_message(BTN_CHANGE_COMPANY)
    await hc.card_change_company(msg, fsm_state)
    assert (
        await fsm_state.get_state() == ContainerSection.choosing_company.state
    )
    assert "Выберите компанию" in msg.answer.call_args[0][0]


async def test_company_selected(test_db, make_message, fsm_state):
    comp_id = await db_comp.add_company(name="Ромашка")
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.choosing_company)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message("🏢 Ромашка")
    await hc.company_selected(msg, fsm_state)
    fresh = await db_cont.get_container(cid)
    assert fresh["company_id"] == comp_id
    assert await fsm_state.get_state() == ContainerSection.card.state


async def test_company_selected_not_button(test_db, make_message, fsm_state):
    """Текст без префикса 🏢 игнорируется."""
    msg = make_message("Ромашка")
    await hc.company_selected(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_company_selected_no_id(test_db, make_message, fsm_state):
    msg = make_message("🏢 Ромашка")
    await hc.company_selected(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_company_selected_unknown(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_data({"container_id": cid})
    msg = make_message("🏢 Нет такой")
    await hc.company_selected(msg, fsm_state)
    assert "не найдена" in msg.answer.call_args[0][0]


async def test_company_cancel_restores_card(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.choosing_company)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message(BTN_CANCEL)
    await hc.company_cancel(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.card.state


# ---------------------------------------------------------------------------
# Карточка: удаление
# ---------------------------------------------------------------------------


async def test_card_delete_ask(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": cid})
    msg = make_message(BTN_DELETE)
    await hc.card_delete_ask(msg, fsm_state)
    assert (
        await fsm_state.get_state()
        == ContainerSection.confirming_delete.state
    )
    assert "Удалить контейнер" in msg.answer.call_args[0][0]


async def test_card_delete_ask_no_id(test_db, make_message, fsm_state):
    msg = make_message(BTN_DELETE)
    await hc.card_delete_ask(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_card_delete_ask_missing_container(
    test_db, make_message, fsm_state
):
    await fsm_state.set_data({"container_id": 999})
    msg = make_message(BTN_DELETE)
    await hc.card_delete_ask(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_delete_confirm(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.confirming_delete)
    await fsm_state.set_data({"container_id": cid})
    msg = make_message(BTN_CONFIRM_DELETE)
    await hc.delete_confirm(msg, fsm_state)
    assert await db_cont.get_container(cid) is None
    assert "Удалено" in msg.answer.call_args_list[0].args[0]
    assert await fsm_state.get_state() == ContainerSection.menu.state


async def test_delete_confirm_no_id(test_db, make_message, fsm_state):
    msg = make_message(BTN_CONFIRM_DELETE)
    await hc.delete_confirm(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_delete_confirm_missing_container(
    test_db, make_message, fsm_state
):
    """Контейнер уже исчез: display «?», удаление не падает."""
    await fsm_state.set_data({"container_id": 999})
    msg = make_message(BTN_CONFIRM_DELETE)
    await hc.delete_confirm(msg, fsm_state)
    assert "Удалено" in msg.answer.call_args_list[0].args[0]
    assert await fsm_state.get_state() == ContainerSection.menu.state


async def test_delete_confirm_notifies_groups(
    test_db, make_message, fsm_state, monkeypatch
):
    """Live-лента: при непустом _group_ids уходит уведомление об удалении."""
    import services.group_notify as gn

    notify = AsyncMock()
    monkeypatch.setattr(gn, "notify_groups", notify)
    comp_id = await db_comp.add_company(name="Ромашка")
    cid = await _seed_container(company_id=comp_id)
    await fsm_state.set_data({"container_id": cid})
    msg = make_message(BTN_CONFIRM_DELETE)
    msg.bot._group_ids = frozenset({-100500})
    await hc.delete_confirm(msg, fsm_state)
    notify.assert_awaited_once()
    notify_text = notify.await_args.args[2]
    assert "Удалён контейнер" in notify_text
    assert "AAAU 1111111" in notify_text
    assert "Ромашка" in notify_text


async def test_delete_cancel_restores_card(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.confirming_delete)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message(BTN_CANCEL)
    await hc.delete_cancel(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.card.state


async def test_delete_fallback_silent(test_db, make_message, fsm_state):
    msg = make_message("что-то")
    await hc.delete_fallback(msg)
    msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Фолбэк карточки (текстовый ввод номера)
# ---------------------------------------------------------------------------


async def test_card_fallback_opens_other_card(test_db, make_message, fsm_state):
    a_id = await _seed_container()
    b_id = await _seed_container(
        number="BBBU2222222", display="BBBU 2222222"
    )
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": a_id, "card_source": "active"})
    msg = make_message("BBBU 2222222")
    await hc.card_fallback(msg, fsm_state, role="full")
    assert (await fsm_state.get_data())["container_id"] == b_id


async def test_card_fallback_filters(test_db, make_message, fsm_state):
    """Роль без доступа, пустой текст и зарезервированные кнопки молчат."""
    msg = make_message("AAAU 1111111")
    await hc.card_fallback(msg, fsm_state, role="none")
    msg.answer.assert_not_called()
    msg2 = make_message("  ")
    await hc.card_fallback(msg2, fsm_state, role="full")
    msg2.answer.assert_not_called()
    msg3 = make_message(BTN_DELETE)
    await hc.card_fallback(msg3, fsm_state, role="full")
    msg3.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Валидация даты вывоза
# ---------------------------------------------------------------------------


def test_validate_departure_future():
    future = datetime.now() + timedelta(days=2)
    assert "в будущем" in hc._validate_departure(future, None)


def test_validate_departure_before_arrival():
    dep = datetime.now() - timedelta(days=5)
    arr = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    assert "раньше даты прибытия" in hc._validate_departure(dep, arr)


def test_validate_departure_ok():
    dep = datetime.now()
    arr = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    assert hc._validate_departure(dep, arr) is None


def test_validate_departure_no_arrival():
    assert hc._validate_departure(datetime.now(), None) is None


# ---------------------------------------------------------------------------
# FSM выбора даты вывоза
# ---------------------------------------------------------------------------


async def test_depart_cancel_restores_card(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerDepart.waiting_for_departure_date)
    await fsm_state.set_data(
        {"container_id": cid, "card_source": "active", "depart_mode": "depart"}
    )
    msg = make_message(BTN_DEPART_CANCEL)
    await hc.depart_cancel_select(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.card.state
    fresh = await db_cont.get_container(cid)
    assert fresh["status"] == "on_terminal"


async def test_depart_cancel_no_id_goes_menu(test_db, make_message, fsm_state):
    msg = make_message(BTN_DEPART_CANCEL)
    await hc.depart_cancel_select(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.menu.state


async def test_depart_cancel_missing_container(
    test_db, make_message, fsm_state
):
    await fsm_state.set_data({"container_id": 999})
    msg = make_message(BTN_DEPART_CANCEL)
    await hc.depart_cancel_select(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.menu.state


async def test_depart_today_success(test_db, make_message, fsm_state):
    arr = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    cid = await _seed_container(arrival=arr)
    await fsm_state.set_state(ContainerDepart.waiting_for_departure_date)
    await fsm_state.set_data(
        {"container_id": cid, "card_source": "active", "depart_mode": "depart"}
    )
    msg = make_message(BTN_DEPART_TODAY)
    await hc.depart_today(msg, fsm_state)
    fresh = await db_cont.get_container(cid)
    assert fresh["status"] == "departed"
    # Формат «Сегодня»: дата в подтверждении не показывается
    confirmation = msg.answer.call_args_list[0].args[0]
    assert confirmation == "✅ Контейнер AAAU 1111111 вывезен."
    assert await fsm_state.get_state() == ContainerSection.card.state


async def test_depart_today_no_id(test_db, make_message, fsm_state):
    msg = make_message(BTN_DEPART_TODAY)
    await hc.depart_today(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_depart_today_missing_container(test_db, make_message, fsm_state):
    await fsm_state.set_data({"container_id": 999})
    msg = make_message(BTN_DEPART_TODAY)
    await hc.depart_today(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.menu.state


async def test_depart_today_before_arrival(test_db, make_message, fsm_state):
    """Прибытие в будущем: «сегодня» раньше прибытия — ошибка валидации."""
    arr = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    cid = await _seed_container(arrival=arr)
    await fsm_state.set_data({"container_id": cid, "depart_mode": "depart"})
    msg = make_message(BTN_DEPART_TODAY)
    await hc.depart_today(msg, fsm_state)
    assert "раньше даты прибытия" in msg.answer.call_args[0][0]
    fresh = await db_cont.get_container(cid)
    assert fresh["status"] == "on_terminal"


async def test_depart_choose_manual(test_db, make_message, fsm_state):
    await fsm_state.set_state(ContainerDepart.waiting_for_departure_date)
    msg = make_message(BTN_DEPART_MANUAL)
    await hc.depart_choose_manual(msg, fsm_state)
    assert (
        await fsm_state.get_state()
        == ContainerDepart.waiting_for_manual_date.state
    )
    assert "ДД.ММ.ГГГГ" in msg.answer.call_args[0][0]


async def test_depart_select_fallback(test_db, make_message, fsm_state):
    msg = make_message("ерунда")
    await hc.depart_select_fallback(msg)
    assert "Выберите вариант" in msg.answer.call_args[0][0]


async def test_depart_cancel_manual(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_state(ContainerDepart.waiting_for_manual_date)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message(BTN_DEPART_CANCEL)
    await hc.depart_cancel_manual(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.card.state


async def test_depart_manual_invalid_format(test_db, make_message, fsm_state):
    msg = make_message("31-02-2026")
    await hc.depart_manual_input(msg, fsm_state)
    assert "Неверный формат" in msg.answer.call_args[0][0]


async def test_depart_manual_no_id(test_db, make_message, fsm_state):
    msg = make_message("01.06.2026")
    await hc.depart_manual_input(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_depart_manual_missing_container(
    test_db, make_message, fsm_state
):
    await fsm_state.set_data({"container_id": 999})
    msg = make_message("01.06.2026")
    await hc.depart_manual_input(msg, fsm_state)
    assert await fsm_state.get_state() == ContainerSection.menu.state


async def test_depart_manual_future_date(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_data({"container_id": cid, "depart_mode": "depart"})
    future = (datetime.now() + timedelta(days=2)).strftime("%d.%m.%Y")
    msg = make_message(future)
    await hc.depart_manual_input(msg, fsm_state)
    assert "в будущем" in msg.answer.call_args[0][0]


async def test_depart_manual_success(test_db, make_message, fsm_state):
    arr = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    cid = await _seed_container(arrival=arr)
    await fsm_state.set_data(
        {"container_id": cid, "card_source": "active", "depart_mode": "depart"}
    )
    dep = datetime.now() - timedelta(days=1)
    msg = make_message(dep.strftime("%d.%m.%Y"))
    await hc.depart_manual_input(msg, fsm_state)
    fresh = await db_cont.get_container(cid)
    assert fresh["status"] == "departed"
    # Ручной ввод: дата показывается в подтверждении
    confirmation = msg.answer.call_args_list[0].args[0]
    assert dep.strftime("%d.%m.%Y") in confirmation
    assert await fsm_state.get_state() == ContainerSection.card.state


async def test_depart_manual_edit_mode(test_db, make_message, fsm_state):
    """Режим edit меняет только дату, статус остаётся departed."""
    cid = await _seed_departed()
    await fsm_state.set_data(
        {"container_id": cid, "card_source": "departed", "depart_mode": "edit"}
    )
    dep = datetime.now() - timedelta(days=2)
    msg = make_message(dep.strftime("%d.%m.%Y"))
    await hc.depart_manual_input(msg, fsm_state)
    fresh = await db_cont.get_container(cid)
    assert fresh["status"] == "departed"
    assert fresh["departure_date"] == dep.strftime("%Y-%m-%d") + " 00:00:00"
    assert "Дата вывоза изменена" in msg.answer.call_args_list[0].args[0]


async def test_finalize_no_id_returns(test_db, make_message, fsm_state):
    msg = make_message()
    await hc._finalize_departure(
        msg, fsm_state, datetime.now(), used_today_button=True
    )
    msg.answer.assert_not_called()


async def test_finalize_missing_container(test_db, make_message, fsm_state):
    """Контейнер исчез между валидацией и сохранением."""
    await fsm_state.set_data({"container_id": 999, "depart_mode": "depart"})
    msg = make_message()
    await hc._finalize_departure(
        msg, fsm_state, datetime.now(), used_today_button=True
    )
    assert "не найден" in msg.answer.call_args_list[0].args[0]
    assert await fsm_state.get_state() == ContainerSection.menu.state


async def test_depart_notifies_groups(
    test_db, make_message, fsm_state, monkeypatch
):
    """Live-лента: уведомление о вывозе с расчётом стоимости и оператором."""
    import services.group_notify as gn

    notify = AsyncMock()
    monkeypatch.setattr(gn, "notify_groups", notify)
    comp_id = await db_comp.add_company(name="Ромашка")
    arr = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    cid = await _seed_container(arrival=arr, company_id=comp_id)
    await fsm_state.set_data(
        {"container_id": cid, "card_source": "active", "depart_mode": "depart"}
    )
    msg = make_message(BTN_DEPART_TODAY)
    msg.bot._group_ids = frozenset({-100500})
    await hc.depart_today(msg, fsm_state)
    notify.assert_awaited_once()
    notify_text = notify.await_args.args[2]
    assert "Вывоз" in notify_text
    assert "Ромашка" in notify_text
    assert "@operator" in notify_text


async def test_depart_notify_username_fallback(
    test_db, make_message, fsm_state, monkeypatch
):
    """Без username в уведомлении используется full_name."""
    import services.group_notify as gn

    notify = AsyncMock()
    monkeypatch.setattr(gn, "notify_groups", notify)
    arr = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    cid = await _seed_container(arrival=arr)
    await fsm_state.set_data(
        {"container_id": cid, "card_source": "active", "depart_mode": "depart"}
    )
    msg = make_message(BTN_DEPART_TODAY)
    msg.from_user.username = None
    msg.bot._group_ids = frozenset({-100500})
    await hc.depart_today(msg, fsm_state)
    assert "Operator" in notify.await_args.args[2]
