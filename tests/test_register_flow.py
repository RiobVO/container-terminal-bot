"""Тесты порядка FSM регистрации: номер → дата → компания → тип."""
from db import containers as db_cont
from handlers import register
from states import ContainerSection, RegisterContainer


async def test_start_registration_asks_date_first(
    test_db, make_message, fsm_state
):
    msg = make_message()
    await register.start_registration(
        msg, fsm_state, "CASS1234567", "CASS 1234567"
    )

    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_arrival_date.state
    )
    assert await fsm_state.get_data() == {
        "number": "CASS1234567",
        "display_number": "CASS 1234567",
    }


async def test_start_registration_clears_card_keys(
    test_db, make_message, fsm_state
):
    """Старт из карточки не тащит container_id в данные регистрации."""
    await fsm_state.set_data({"container_id": 99, "card_source": "active"})
    msg = make_message()
    await register.start_registration(
        msg, fsm_state, "CASS1234567", "CASS 1234567"
    )

    data = await fsm_state.get_data()
    assert "container_id" not in data
    assert "card_source" not in data


async def test_arrival_today_goes_to_company(test_db, make_message, fsm_state):
    await fsm_state.set_state(RegisterContainer.waiting_for_arrival_date)
    await fsm_state.set_data(
        {"number": "CASS1234567", "display_number": "CASS 1234567"}
    )
    msg = make_message()
    await register.arrival_today(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_company.state
    )
    data = await fsm_state.get_data()
    assert data["status"] == "on_terminal"
    assert data["arrival_date"] is not None


async def test_arrival_transit_goes_to_company(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(RegisterContainer.waiting_for_arrival_date)
    await fsm_state.set_data(
        {"number": "CASS1234567", "display_number": "CASS 1234567"}
    )
    msg = make_message()
    await register.arrival_transit(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_company.state
    )
    data = await fsm_state.get_data()
    assert data["status"] == "in_transit"
    assert data["arrival_date"] is None


async def test_manual_date_goes_to_company(test_db, make_message, fsm_state):
    await fsm_state.set_state(RegisterContainer.waiting_for_manual_date)
    await fsm_state.set_data(
        {"number": "CASS1234567", "display_number": "CASS 1234567"}
    )
    msg = make_message("01.06.2026")
    await register.manual_date_process(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_company.state
    )
    data = await fsm_state.get_data()
    assert data["status"] == "on_terminal"
    assert data["arrival_date"] == "2026-06-01 00:00:00"


async def test_process_company_goes_to_type(test_db, make_message, fsm_state):
    await fsm_state.set_state(RegisterContainer.waiting_for_company)
    await fsm_state.set_data(
        {
            "number": "CASS1234567",
            "display_number": "CASS 1234567",
            "status": "on_terminal",
            "arrival_date": "2026-06-01 10:00:00",
        }
    )
    msg = make_message("Ромашка")
    await register.process_company(msg, fsm_state, role="full")

    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_type.state
    )
    data = await fsm_state.get_data()
    assert data["company_name"] == "Ромашка"
    assert isinstance(data["company_id"], int)


async def test_full_flow_creates_container(test_db, make_message, fsm_state):
    """Сквозной happy-path: дата → компания → тип → запись в БД."""
    await register.start_registration(
        make_message(), fsm_state, "CASS1234567", "CASS 1234567"
    )
    await register.arrival_today(make_message(), fsm_state)
    await register.process_company(
        make_message("Ромашка"), fsm_state, role="full"
    )
    await register.type_selected(make_message("40HQ"), fsm_state, role="full")

    container = await db_cont.find_by_number("CASS1234567")
    assert container is not None
    assert container["type"] == "40HQ"
    assert container["company_name"] == "Ромашка"
    assert container["status"] == "on_terminal"
    # После регистрации показывается карточка — FSM в ContainerSection.card,
    # откуда (Task 4) принимается номер следующего контейнера.
    assert await fsm_state.get_state() == ContainerSection.card.state
