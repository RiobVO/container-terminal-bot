"""Тесты ввода номера контейнера в состоянии карточки (card_fallback)."""
from db import companies as db_comp
from db import containers as db_cont
from handlers.containers import card_fallback
from keyboards.containers import BTN_DEPART
from states import ContainerSection, RegisterContainer


async def _seed_container(number: str, display: str) -> int:
    company_id = await db_comp.add_company(name="Ромашка")
    return await db_cont.add_container(
        number=number,
        display_number=display,
        company_id=company_id,
        status="on_terminal",
        arrival_date="2026-06-01 10:00:00",
    )


async def test_card_existing_number_opens_its_card(
    test_db, make_message, fsm_state
):
    a_id = await _seed_container("AAAU1111111", "AAAU 1111111")
    b_id = await db_cont.add_container(
        number="BBBU2222222",
        display_number="BBBU 2222222",
        company_id=None,
        status="on_terminal",
        arrival_date="2026-06-02 10:00:00",
    )
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": a_id, "card_source": "active"})

    msg = make_message("bbbu 2222222")
    await card_fallback(msg, fsm_state, role="full")

    assert await fsm_state.get_state() == ContainerSection.card.state
    data = await fsm_state.get_data()
    assert data["container_id"] == b_id
    assert "BBBU 2222222" in msg.answer.call_args[0][0]


async def test_card_new_number_starts_registration(
    test_db, make_message, fsm_state
):
    a_id = await _seed_container("AAAU1111111", "AAAU 1111111")
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": a_id, "card_source": "active"})

    msg = make_message("HLXU 7777777")
    await card_fallback(msg, fsm_state, role="full")

    assert (
        await fsm_state.get_state()
        == RegisterContainer.waiting_for_company.state
    )
    assert await fsm_state.get_data() == {
        "number": "HLXU7777777",
        "display_number": "HLXU 7777777",
    }


async def test_card_invalid_number_answers_error(
    test_db, make_message, fsm_state
):
    """Опечатка в номере получает явную ошибку, а не молчание."""
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": 1, "card_source": "active"})

    msg = make_message("CASS123456")  # 6 цифр вместо 7
    await card_fallback(msg, fsm_state, role="full")

    assert msg.answer.call_count == 1
    assert "Неверный формат" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() == ContainerSection.card.state


async def test_card_same_number_reopens_card(test_db, make_message, fsm_state):
    """Повторный ввод номера текущей карточки просто открывает её заново."""
    a_id = await _seed_container("AAAU1111111", "AAAU 1111111")
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": a_id, "card_source": "active"})

    msg = make_message("AAAU 1111111")
    await card_fallback(msg, fsm_state, role="full")

    assert await fsm_state.get_state() == ContainerSection.card.state
    assert (await fsm_state.get_data())["container_id"] == a_id
    assert "AAAU 1111111" in msg.answer.call_args[0][0]


async def test_card_reserved_button_ignored(test_db, make_message, fsm_state):
    await fsm_state.set_state(ContainerSection.card)
    msg = make_message(BTN_DEPART)
    await card_fallback(msg, fsm_state, role="full")
    msg.answer.assert_not_called()


async def test_card_no_access_role_ignored(test_db, make_message, fsm_state):
    await fsm_state.set_state(ContainerSection.card)
    msg = make_message("HLXU 7777777")
    await card_fallback(msg, fsm_state, role="reports_only")
    msg.answer.assert_not_called()
