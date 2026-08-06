"""Тесты порядка FSM регистрации: номер → дата → компания → тип."""
from db import companies as db_comp
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
    # Шаг компании показывает выбранную дату
    assert "📅 Прибыл:" in msg.answer.call_args[0][0]


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
    # Шаг компании показывает транзитный статус, а не «Прибыл: —»
    assert "Ещё в пути" in msg.answer.call_args[0][0]


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
    assert "01.06.2026" in msg.answer.call_args[0][0]


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


async def test_process_company_rejects_container_number(
    test_db, make_message, fsm_state
):
    """Номер следующего контейнера на шаге компании не создаёт компанию."""
    await fsm_state.set_state(RegisterContainer.waiting_for_company)
    await fsm_state.set_data(
        {
            "number": "CASS1234567",
            "display_number": "CASS 1234567",
            "status": "on_terminal",
            "arrival_date": "2026-06-01 10:00:00",
        }
    )
    msg = make_message("TEMU 7654321")
    await register.process_company(msg, fsm_state, role="full")

    assert await db_comp.list_companies() == []
    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_company.state
    )
    assert "похоже на номер" in msg.answer.call_args[0][0].lower()


async def test_process_company_stale_session_resets(
    test_db, make_message, fsm_state
):
    """Состояние без данных (пережило деплой) — мягкий сброс, не KeyError."""
    await fsm_state.set_state(RegisterContainer.waiting_for_company)
    msg = make_message("Ромашка")
    await register.process_company(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert "устарела" in msg.answer.call_args[0][0].lower()
    assert await db_comp.list_companies() == []


async def test_finalize_incomplete_data_resets(
    test_db, make_message, fsm_state
):
    """Сессия старого порядка шагов без company_id/status не падает."""
    await fsm_state.set_state(RegisterContainer.waiting_for_type)
    await fsm_state.set_data(
        {"number": "CASS1234567", "display_number": "CASS 1234567"}
    )
    msg = make_message()
    await register.type_skip(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert await db_cont.find_by_number("CASS1234567") is None
    assert "устарела" in msg.answer.call_args[0][0].lower()


async def test_process_company_old_order_session_resets(
    test_db, make_message, fsm_state
):
    """Сессия старого порядка (номер есть, даты нет) не создаёт компанию-сироту."""
    await fsm_state.set_state(RegisterContainer.waiting_for_company)
    await fsm_state.set_data(
        {"number": "CASS1234567", "display_number": "CASS 1234567"}
    )
    msg = make_message("Ромашка")
    await register.process_company(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert await db_comp.list_companies() == []
    assert "устарела" in msg.answer.call_args[0][0].lower()


async def test_company_cancel_creates_nothing(
    test_db, make_message, fsm_state
):
    """«◀ Отмена» на шаге компании чистит FSM и не создаёт компанию."""
    from keyboards.register import BTN_REG_CANCEL

    await fsm_state.set_state(RegisterContainer.waiting_for_company)
    await fsm_state.set_data(
        {
            "number": "CASS1234567",
            "display_number": "CASS 1234567",
            "status": "on_terminal",
            "arrival_date": "2026-06-01 10:00:00",
        }
    )
    msg = make_message(BTN_REG_CANCEL)
    await register.company_cancel(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert await db_comp.list_companies() == []


async def test_process_company_existing_no_duplicate(
    test_db, make_message, fsm_state
):
    """Существующая компания матчится регистронезависимо, дубликат не создаётся."""
    existing_id = await db_comp.add_company(name="Acme")
    await fsm_state.set_state(RegisterContainer.waiting_for_company)
    await fsm_state.set_data(
        {
            "number": "CASS1234567",
            "display_number": "CASS 1234567",
            "status": "on_terminal",
            "arrival_date": "2026-06-01 10:00:00",
        }
    )
    msg = make_message("acme")
    await register.process_company(msg, fsm_state, role="full")

    data = await fsm_state.get_data()
    assert data["company_id"] == existing_id
    assert data["company_name"] == "Acme"
    assert len(await db_comp.list_companies()) == 1


async def test_finalize_duplicate_opens_existing_card(
    test_db, make_message, fsm_state
):
    """Гонка регистрации: дубликат не падает, открывается карточка существующего."""
    company_id = await db_comp.add_company(name="Ромашка")
    existing_id = await db_cont.add_container(
        number="CASS1234567",
        display_number="CASS 1234567",
        company_id=company_id,
        status="on_terminal",
        arrival_date="2026-06-01 10:00:00",
    )
    await fsm_state.set_state(RegisterContainer.waiting_for_type)
    await fsm_state.set_data(
        {
            "number": "CASS1234567",
            "display_number": "CASS 1234567",
            "company_id": company_id,
            "company_name": "Ромашка",
            "status": "on_terminal",
            "arrival_date": "2026-06-02 10:00:00",
        }
    )
    msg = make_message()
    await register.type_skip(msg, fsm_state, role="full")

    texts = [c.args[0] for c in msg.answer.call_args_list]
    assert any("уже зарегистрирован" in t for t in texts)
    assert await fsm_state.get_state() == ContainerSection.card.state
    assert (await fsm_state.get_data())["container_id"] == existing_id
