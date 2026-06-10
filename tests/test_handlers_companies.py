"""Тесты раздела «Компании»: список, карточка, создание, переименование,
тарифные параметры (NULL = стандартный), удаление, отказ в доступе."""
from db import companies as db_comp
from db import containers as db_cont
from handlers import companies as h
from keyboards.companies import (
    BTN_CANCEL_X,
    BTN_CONFIRM_DELETE,
)
from states import (
    CompaniesSection,
    EditCompanyEntry,
    EditCompanyFreeDays,
    EditCompanyName,
    EditCompanyStoragePeriod,
    EditCompanyStorageRate,
)


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _answers(msg) -> list[str]:
    """Все тексты, отправленные через msg.answer."""
    return [c.args[0] for c in msg.answer.call_args_list]


async def _seed_custom_company() -> int:
    """Компания со всеми четырьмя индивидуальными параметрами."""
    return await db_comp.add_company(
        name="Custom Co",
        entry_fee=100.0,
        free_days=0,
        storage_rate=10.0,
        storage_period_days=7,
    )


async def _put_in_card(state, company_id: int) -> None:
    """Имитирует нахождение пользователя в карточке компании."""
    await state.set_state(CompaniesSection.card)
    await state.update_data(company_id=company_id)


# ---------------------------------------------------------------------------
# Вход в раздел / роли
# ---------------------------------------------------------------------------


async def test_menu_denied_for_operator(test_db, make_message, fsm_state):
    """Не-full роль получает отказ, состояние не меняется."""
    msg = make_message()
    await h.companies_menu(msg, fsm_state, role="operator")

    assert "нет доступа" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() is None


async def test_menu_empty_list(test_db, make_message, fsm_state):
    """Без компаний — заглушка и пустой мэппинг."""
    msg = make_message()
    await h.companies_menu(msg, fsm_state, role="full")

    assert any("Компаний пока нет" in t for t in _answers(msg))
    assert await fsm_state.get_state() == CompaniesSection.list.state
    assert (await fsm_state.get_data())["companies_map"] == {}


async def test_menu_with_companies(test_db, make_message, fsm_state):
    """С компаниями — список с клавиатурой и мэппингом текст→id."""
    cid = await db_comp.add_company(name="Acme")
    msg = make_message()
    await h.companies_menu(msg, fsm_state, role="full")

    assert any("Выберите компанию" in t for t in _answers(msg))
    mapping = (await fsm_state.get_data())["companies_map"]
    assert mapping == {"🏢 Acme (0)": cid}


async def test_companies_back_to_main_menu(test_db, make_message, fsm_state):
    await fsm_state.set_state(CompaniesSection.list)
    msg = make_message()
    await h.companies_back(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert "Главное меню" in msg.answer.call_args[0][0]


# ---------------------------------------------------------------------------
# Список: выбор компании
# ---------------------------------------------------------------------------


async def test_list_select_unknown_text_ignored(
    test_db, make_message, fsm_state
):
    """Текст вне мэппинга молча игнорируется."""
    await fsm_state.set_state(CompaniesSection.list)
    await fsm_state.set_data({"companies_map": {"🏢 Acme (0)": 1}})
    msg = make_message("что-то постороннее")
    await h.companies_list_select(msg, fsm_state)

    msg.answer.assert_not_called()
    assert await fsm_state.get_state() == CompaniesSection.list.state


async def test_list_select_opens_card(test_db, make_message, fsm_state):
    cid = await db_comp.add_company(name="Acme")
    await fsm_state.set_state(CompaniesSection.list)
    await fsm_state.set_data({"companies_map": {"🏢 Acme (0)": cid}})
    msg = make_message("🏢 Acme (0)")
    await h.companies_list_select(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.card.state
    assert (await fsm_state.get_data())["company_id"] == cid


async def test_list_select_missing_company_back_to_list(
    test_db, make_message, fsm_state
):
    """Компания удалена между показом списка и кликом — мягкий возврат."""
    await fsm_state.set_state(CompaniesSection.list)
    await fsm_state.set_data({"companies_map": {"🏢 Ghost (0)": 999}})
    msg = make_message("🏢 Ghost (0)")
    await h.companies_list_select(msg, fsm_state)

    assert any("не найдена" in t for t in _answers(msg))
    assert await fsm_state.get_state() == CompaniesSection.list.state


# ---------------------------------------------------------------------------
# Карточка компании: содержимое
# ---------------------------------------------------------------------------


async def test_card_custom_tariffs_and_containers(
    test_db, make_message, fsm_state
):
    """Карточка: индивидуальные тарифы, долг по on_terminal, форматы дат."""
    cid = await _seed_custom_company()
    # on_terminal с полной датой — попадает в расчёт долга
    await db_cont.add_container(
        number="TEMU1234567", display_number="TEMU 1234567",
        company_id=cid, status="on_terminal",
        arrival_date="2026-06-01 10:00:00",
    )
    # in_transit без даты — ветка «—»
    await db_cont.add_container(
        number="TEMU1234568", display_number="TEMU 1234568",
        company_id=cid, status="in_transit", arrival_date=None,
    )
    # короткий формат даты — вторая ветка _fmt_short_date
    await db_cont.add_container(
        number="TEMU1234569", display_number="TEMU 1234569",
        company_id=cid, status="in_transit", arrival_date="2026-06-02",
    )
    # непарсибельная дата — фолбэк «как есть»
    await db_cont.add_container(
        number="TEMU1234570", display_number="TEMU 1234570",
        company_id=cid, status="in_transit", arrival_date="когда-то",
    )
    # departed — не активный, но входит в total_ever
    await db_cont.add_container(
        number="TEMU1234571", display_number="TEMU 1234571",
        company_id=cid, status="departed",
        arrival_date="2026-05-01 10:00:00",
    )

    msg = make_message()
    await h._show_company_card(msg, fsm_state, cid)

    text = msg.answer.call_args[0][0]
    assert "Custom Co" in text
    assert "100.0 $ (индивидуальный)" in text
    assert "каждые 7 дн." in text
    assert "Занятых контейнеров: 4" in text
    assert "Всего контейнеров за время: 5" in text
    assert "01.06.2026" in text
    assert "02.06.2026" in text
    assert "когда-то" in text
    assert "с —" in text
    # entry 100 + хранение > 0 при free_days=0
    assert "К оплате: 0.00" not in text
    assert await fsm_state.get_state() == CompaniesSection.card.state


async def test_card_default_tariffs_no_containers(
    test_db, make_message, fsm_state
):
    """Все параметры NULL — подставляются стандартные, метка «стандартный»."""
    cid = await db_comp.add_company(name="Plain Co")
    msg = make_message()
    await h._show_company_card(msg, fsm_state, cid)

    text = msg.answer.call_args[0][0]
    assert "стандартный" in text
    assert "индивидуальный" not in text
    assert "ежемесячный тариф" in text
    assert "К оплате: 0.00 $" in text
    assert "Активные контейнеры:\n—" in text.replace("<b>", "").replace(
        "</b>", ""
    )


async def test_card_daily_period_label(test_db, make_message, fsm_state):
    """storage_period_days=1 — метка «ежедневный тариф»."""
    cid = await db_comp.add_company(name="Daily Co", storage_period_days=1)
    msg = make_message()
    await h._show_company_card(msg, fsm_state, cid)

    assert "ежедневный тариф" in msg.answer.call_args[0][0]


async def test_card_back_to_list(test_db, make_message, fsm_state):
    cid = await db_comp.add_company(name="Acme")
    await _put_in_card(fsm_state, cid)
    msg = make_message()
    await h.card_back(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.list.state


# ---------------------------------------------------------------------------
# Создание компании
# ---------------------------------------------------------------------------


async def test_add_start(test_db, make_message, fsm_state):
    await fsm_state.set_state(CompaniesSection.list)
    msg = make_message()
    await h.companies_add_start(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.adding_name.state
    assert "Добавление новой компании" in msg.answer.call_args[0][0]


async def test_add_cancel_returns_to_list(test_db, make_message, fsm_state):
    await fsm_state.set_state(CompaniesSection.adding_name)
    msg = make_message(BTN_CANCEL_X)
    await h.companies_add_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.list.state
    assert await db_comp.list_companies() == []


async def test_add_empty_name_rejected(test_db, make_message, fsm_state):
    await fsm_state.set_state(CompaniesSection.adding_name)
    msg = make_message("   ")
    await h.companies_add_process(msg, fsm_state)

    assert "от 1 до 64" in msg.answer.call_args[0][0]
    assert await db_comp.list_companies() == []
    assert await fsm_state.get_state() == CompaniesSection.adding_name.state


async def test_add_too_long_name_rejected(test_db, make_message, fsm_state):
    await fsm_state.set_state(CompaniesSection.adding_name)
    msg = make_message("X" * 65)
    await h.companies_add_process(msg, fsm_state)

    assert "от 1 до 64" in msg.answer.call_args[0][0]
    assert await db_comp.list_companies() == []


async def test_add_duplicate_rejected(test_db, make_message, fsm_state):
    """Дубликат матчится регистронезависимо."""
    await db_comp.add_company(name="Acme")
    await fsm_state.set_state(CompaniesSection.adding_name)
    msg = make_message("acme")
    await h.companies_add_process(msg, fsm_state)

    assert "уже существует" in msg.answer.call_args[0][0]
    assert len(await db_comp.list_companies()) == 1


async def test_add_success_opens_card(test_db, make_message, fsm_state):
    await fsm_state.set_state(CompaniesSection.adding_name)
    msg = make_message("Новая")
    await h.companies_add_process(msg, fsm_state)

    created = await db_comp.get_company_by_name_ci("Новая")
    assert created is not None
    assert any("создана" in t for t in _answers(msg))
    assert await fsm_state.get_state() == CompaniesSection.card.state
    assert (await fsm_state.get_data())["company_id"] == created["id"]


# ---------------------------------------------------------------------------
# Вход в редакторы тарифных полей
# ---------------------------------------------------------------------------


async def test_card_edit_entry_custom(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await _put_in_card(fsm_state, cid)
    msg = make_message()
    await h.card_edit_entry(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == EditCompanyEntry.waiting_for_value.state
    )
    text = msg.answer.call_args[0][0]
    assert "Стоимость входа" in text
    assert "100.0 $ (индивидуальный)" in text


async def test_card_edit_entry_default(test_db, make_message, fsm_state):
    """NULL-параметр — показывается стандартное значение."""
    cid = await db_comp.add_company(name="Plain Co")
    await _put_in_card(fsm_state, cid)
    msg = make_message()
    await h.card_edit_entry(msg, fsm_state)

    assert "(стандартный)" in msg.answer.call_args[0][0]


async def test_card_edit_free_days(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await _put_in_card(fsm_state, cid)
    msg = make_message()
    await h.card_edit_free_days(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == EditCompanyFreeDays.waiting_for_value.state
    )
    assert "Бесплатные дни" in msg.answer.call_args[0][0]


async def test_card_edit_storage_rate(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await _put_in_card(fsm_state, cid)
    msg = make_message()
    await h.card_edit_storage_rate(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == EditCompanyStorageRate.waiting_for_value.state
    )
    assert "Ставка платного хранения" in msg.answer.call_args[0][0]


async def test_card_edit_storage_period(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await _put_in_card(fsm_state, cid)
    msg = make_message()
    await h.card_edit_storage_period(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == EditCompanyStoragePeriod.waiting_for_value.state
    )
    text = msg.answer.call_args[0][0]
    assert "Период начисления" in text
    assert "каждые 7 дн." in text


async def test_card_edit_handlers_missing_company(
    test_db, make_message, fsm_state
):
    """Компания исчезла — все четыре входа в редактор молча выходят."""
    await _put_in_card(fsm_state, 999)
    for handler in (
        h.card_edit_entry,
        h.card_edit_free_days,
        h.card_edit_storage_rate,
        h.card_edit_storage_period,
    ):
        msg = make_message()
        await handler(msg, fsm_state)
        msg.answer.assert_not_called()
        assert await fsm_state.get_state() == CompaniesSection.card.state


async def test_begin_edit_field_guards(test_db, make_message, fsm_state):
    """Гварды _begin_edit_field: нет company_id в данных / компания удалена."""
    msg = make_message()
    await h._begin_edit_field(
        msg, fsm_state, EditCompanyEntry.waiting_for_value,
        title="t", current_text="c", prompt="p",
    )
    msg.answer.assert_not_called()

    await fsm_state.update_data(company_id=999)
    msg = make_message()
    await h._begin_edit_field(
        msg, fsm_state, EditCompanyEntry.waiting_for_value,
        title="t", current_text="c", prompt="p",
    )
    msg.answer.assert_not_called()
    assert await fsm_state.get_state() is None


# ---------------------------------------------------------------------------
# Редактор: стоимость входа
# ---------------------------------------------------------------------------


async def test_edit_entry_cancel(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyEntry.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message(BTN_CANCEL_X)
    await h.edit_entry_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.card.state
    company = await db_comp.get_company(cid)
    assert company["entry_fee"] == 100.0  # не изменилось


async def test_edit_entry_cancel_without_company_id(
    test_db, make_message, fsm_state
):
    """Потерянный company_id в _return_to_card — возврат в список."""
    await fsm_state.set_state(EditCompanyEntry.waiting_for_value)
    msg = make_message(BTN_CANCEL_X)
    await h.edit_entry_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.list.state


async def test_edit_entry_reset_to_default(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyEntry.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message()
    await h.edit_entry_reset(msg, fsm_state)

    assert (await db_comp.get_company(cid))["entry_fee"] is None
    assert any("Сброшено" in t for t in _answers(msg))
    assert await fsm_state.get_state() == CompaniesSection.card.state


async def test_edit_entry_invalid_text(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyEntry.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message("abc")
    await h.edit_entry_value(msg, fsm_state)

    assert "Введите число" in msg.answer.call_args[0][0]
    assert (await db_comp.get_company(cid))["entry_fee"] == 100.0
    assert (
        await fsm_state.get_state()
        == EditCompanyEntry.waiting_for_value.state
    )


async def test_edit_entry_negative_rejected(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyEntry.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message("-5")
    await h.edit_entry_value(msg, fsm_state)

    assert "Введите число" in msg.answer.call_args[0][0]
    assert (await db_comp.get_company(cid))["entry_fee"] == 100.0


async def test_edit_entry_comma_decimal_saved(
    test_db, make_message, fsm_state
):
    """Запятая как десятичный разделитель принимается."""
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyEntry.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message("25,5")
    await h.edit_entry_value(msg, fsm_state)

    assert (await db_comp.get_company(cid))["entry_fee"] == 25.5
    assert await fsm_state.get_state() == CompaniesSection.card.state


# ---------------------------------------------------------------------------
# Редактор: бесплатные дни
# ---------------------------------------------------------------------------


async def test_edit_free_cancel(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyFreeDays.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message(BTN_CANCEL_X)
    await h.edit_free_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.card.state


async def test_edit_free_reset(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyFreeDays.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message()
    await h.edit_free_reset(msg, fsm_state)

    assert (await db_comp.get_company(cid))["free_days"] is None


async def test_edit_free_invalid(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyFreeDays.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    for bad in ("abc", "-1", "1.5"):
        msg = make_message(bad)
        await h.edit_free_value(msg, fsm_state)
        assert "целое число" in msg.answer.call_args[0][0]
    assert (await db_comp.get_company(cid))["free_days"] == 0


async def test_edit_free_valid(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyFreeDays.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message("15")
    await h.edit_free_value(msg, fsm_state)

    assert (await db_comp.get_company(cid))["free_days"] == 15
    assert await fsm_state.get_state() == CompaniesSection.card.state


# ---------------------------------------------------------------------------
# Редактор: ставка хранения
# ---------------------------------------------------------------------------


async def test_edit_rate_cancel(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyStorageRate.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message(BTN_CANCEL_X)
    await h.edit_rate_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.card.state


async def test_edit_rate_reset(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyStorageRate.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message()
    await h.edit_rate_reset(msg, fsm_state)

    assert (await db_comp.get_company(cid))["storage_rate"] is None


async def test_edit_rate_invalid(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyStorageRate.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    for bad in ("abc", "-0.5"):
        msg = make_message(bad)
        await h.edit_rate_value(msg, fsm_state)
        assert "Введите число" in msg.answer.call_args[0][0]
    assert (await db_comp.get_company(cid))["storage_rate"] == 10.0


async def test_edit_rate_valid(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyStorageRate.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message("0.5")
    await h.edit_rate_value(msg, fsm_state)

    assert (await db_comp.get_company(cid))["storage_rate"] == 0.5
    assert await fsm_state.get_state() == CompaniesSection.card.state


# ---------------------------------------------------------------------------
# Редактор: период начисления
# ---------------------------------------------------------------------------


async def test_edit_period_cancel(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyStoragePeriod.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message(BTN_CANCEL_X)
    await h.edit_period_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.card.state


async def test_edit_period_reset(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyStoragePeriod.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message()
    await h.edit_period_reset(msg, fsm_state)

    assert (await db_comp.get_company(cid))["storage_period_days"] is None


async def test_edit_period_invalid(test_db, make_message, fsm_state):
    """Период < 1 и нечисловой ввод отклоняются."""
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyStoragePeriod.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    for bad in ("0", "-3", "abc"):
        msg = make_message(bad)
        await h.edit_period_value(msg, fsm_state)
        assert "целое число ≥ 1" in msg.answer.call_args[0][0]
    assert (await db_comp.get_company(cid))["storage_period_days"] == 7


async def test_edit_period_valid(test_db, make_message, fsm_state):
    cid = await _seed_custom_company()
    await fsm_state.set_state(EditCompanyStoragePeriod.waiting_for_value)
    await fsm_state.update_data(company_id=cid)
    msg = make_message("1")
    await h.edit_period_value(msg, fsm_state)

    assert (await db_comp.get_company(cid))["storage_period_days"] == 1
    assert await fsm_state.get_state() == CompaniesSection.card.state


# ---------------------------------------------------------------------------
# Переименование
# ---------------------------------------------------------------------------


async def test_rename_start(test_db, make_message, fsm_state):
    cid = await db_comp.add_company(name="Old Name")
    await _put_in_card(fsm_state, cid)
    msg = make_message()
    await h.card_rename(msg, fsm_state)

    assert (
        await fsm_state.get_state() == EditCompanyName.waiting_for_name.state
    )
    assert "Old Name" in msg.answer.call_args[0][0]


async def test_rename_start_guards(test_db, make_message, fsm_state):
    """Нет company_id / компания удалена — молчаливый выход."""
    await fsm_state.set_state(CompaniesSection.card)
    msg = make_message()
    await h.card_rename(msg, fsm_state)
    msg.answer.assert_not_called()

    await fsm_state.update_data(company_id=999)
    msg = make_message()
    await h.card_rename(msg, fsm_state)
    msg.answer.assert_not_called()
    assert await fsm_state.get_state() == CompaniesSection.card.state


async def test_rename_cancel(test_db, make_message, fsm_state):
    cid = await db_comp.add_company(name="Old Name")
    await fsm_state.set_state(EditCompanyName.waiting_for_name)
    await fsm_state.update_data(company_id=cid)
    msg = make_message(BTN_CANCEL_X)
    await h.rename_cancel(msg, fsm_state)

    assert (await db_comp.get_company(cid))["name"] == "Old Name"
    assert await fsm_state.get_state() == CompaniesSection.card.state


async def test_rename_invalid_name(test_db, make_message, fsm_state):
    cid = await db_comp.add_company(name="Old Name")
    await fsm_state.set_state(EditCompanyName.waiting_for_name)
    await fsm_state.update_data(company_id=cid)
    for bad in ("", "Y" * 65):
        msg = make_message(bad)
        await h.rename_process(msg, fsm_state)
        assert "от 1 до 64" in msg.answer.call_args[0][0]
    assert (await db_comp.get_company(cid))["name"] == "Old Name"


async def test_rename_duplicate_other_company(
    test_db, make_message, fsm_state
):
    """Имя занято другой компанией — отказ."""
    await db_comp.add_company(name="Taken")
    cid = await db_comp.add_company(name="Old Name")
    await fsm_state.set_state(EditCompanyName.waiting_for_name)
    await fsm_state.update_data(company_id=cid)
    msg = make_message("taken")
    await h.rename_process(msg, fsm_state)

    assert "уже существует" in msg.answer.call_args[0][0]
    assert (await db_comp.get_company(cid))["name"] == "Old Name"


async def test_rename_same_company_case_change(
    test_db, make_message, fsm_state
):
    """Смена регистра собственного имени — разрешена (existing.id == свой)."""
    cid = await db_comp.add_company(name="acme")
    await fsm_state.set_state(EditCompanyName.waiting_for_name)
    await fsm_state.update_data(company_id=cid)
    msg = make_message("ACME")
    await h.rename_process(msg, fsm_state)

    assert (await db_comp.get_company(cid))["name"] == "ACME"
    assert await fsm_state.get_state() == CompaniesSection.card.state


async def test_rename_success(test_db, make_message, fsm_state):
    cid = await db_comp.add_company(name="Old Name")
    await fsm_state.set_state(EditCompanyName.waiting_for_name)
    await fsm_state.update_data(company_id=cid)
    msg = make_message("New Name")
    await h.rename_process(msg, fsm_state)

    assert (await db_comp.get_company(cid))["name"] == "New Name"
    assert await fsm_state.get_state() == CompaniesSection.card.state


# ---------------------------------------------------------------------------
# Удаление
# ---------------------------------------------------------------------------


async def test_delete_ask(test_db, make_message, fsm_state):
    cid = await db_comp.add_company(name="Doomed")
    await _put_in_card(fsm_state, cid)
    msg = make_message()
    await h.card_delete_ask(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == CompaniesSection.confirming_delete.state
    )
    assert "Удалить компанию" in msg.answer.call_args[0][0]


async def test_delete_ask_guards(test_db, make_message, fsm_state):
    """Нет company_id / компания удалена — молчаливый выход."""
    await fsm_state.set_state(CompaniesSection.card)
    msg = make_message()
    await h.card_delete_ask(msg, fsm_state)
    msg.answer.assert_not_called()

    await fsm_state.update_data(company_id=999)
    msg = make_message()
    await h.card_delete_ask(msg, fsm_state)
    msg.answer.assert_not_called()


async def test_delete_cancel_returns_to_card(
    test_db, make_message, fsm_state
):
    cid = await db_comp.add_company(name="Doomed")
    await fsm_state.set_state(CompaniesSection.confirming_delete)
    await fsm_state.update_data(company_id=cid)
    msg = make_message(BTN_CANCEL_X)
    await h.delete_cancel(msg, fsm_state)

    assert await db_comp.get_company(cid) is not None
    assert await fsm_state.get_state() == CompaniesSection.card.state


async def test_delete_cancel_without_company_id(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(CompaniesSection.confirming_delete)
    msg = make_message(BTN_CANCEL_X)
    await h.delete_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.list.state


async def test_delete_confirm_success(test_db, make_message, fsm_state):
    cid = await db_comp.add_company(name="Doomed")
    await fsm_state.set_state(CompaniesSection.confirming_delete)
    await fsm_state.update_data(company_id=cid)
    msg = make_message(BTN_CONFIRM_DELETE)
    await h.delete_confirm(msg, fsm_state)

    assert await db_comp.get_company(cid) is None
    assert any("удалена" in t for t in _answers(msg))
    assert await fsm_state.get_state() == CompaniesSection.list.state


async def test_delete_confirm_without_company_id(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(CompaniesSection.confirming_delete)
    msg = make_message(BTN_CONFIRM_DELETE)
    await h.delete_confirm(msg, fsm_state)

    msg.answer.assert_not_called()


async def test_delete_confirm_missing_company(
    test_db, make_message, fsm_state
):
    """Компания уже удалена — мягкий возврат в список."""
    await fsm_state.set_state(CompaniesSection.confirming_delete)
    await fsm_state.update_data(company_id=999)
    msg = make_message(BTN_CONFIRM_DELETE)
    await h.delete_confirm(msg, fsm_state)

    assert await fsm_state.get_state() == CompaniesSection.list.state


async def test_delete_fallback_silent(test_db, make_message, fsm_state):
    await fsm_state.set_state(CompaniesSection.confirming_delete)
    msg = make_message("посторонний текст")
    await h.delete_fallback(msg)

    msg.answer.assert_not_called()
