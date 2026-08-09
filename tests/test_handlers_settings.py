"""Тесты handlers/settings.py: тарифы по умолчанию и роли пользователей.

_cfg в модуле создаётся на import-time из env — для детерминизма
подменяем его SimpleNamespace с admin_ids={111111} (как в test_db).
"""
from types import SimpleNamespace

import pytest

from db import get_db
from db import users as db_users
from db.settings import get_setting
from handlers import settings as hs
from services import formatters as fmt
from keyboards.main import BTN_BACK, BTN_SETTINGS
from keyboards.settings import (
    BTN_CANCEL_BACK,
    BTN_DEF_ENTRY,
    BTN_DEF_FREE,
    BTN_DEF_STORAGE_PERIOD,
    BTN_DEF_STORAGE_RATE,
    BTN_ROLE_OPERATOR,
    BTN_SET_DEFAULTS,
    BTN_SET_USERS,
)
from states import (
    DefaultsSection,
    EditDefaultEntry,
    EditDefaultFreeDays,
    EditDefaultStoragePeriod,
    EditDefaultStorageRate,
    SettingsSection,
    UsersSection,
)

ADMIN_ID = 111111
REGULAR_ID = 222222


@pytest.fixture(autouse=True)
def patched_cfg(monkeypatch):
    """Фиксирует admin_ids независимо от локального .env."""
    monkeypatch.setattr(
        hs, "_cfg", SimpleNamespace(admin_ids=frozenset({ADMIN_ID}))
    )


async def _add_regular_user() -> None:
    """Создаёт обычного пользователя (не из ADMIN_IDS)."""
    await db_users.upsert_user(
        tg_id=REGULAR_ID,
        username="bob",
        full_name="Bob",
        admin_ids=frozenset(),
    )


async def _clear_users() -> None:
    """Удаляет всех пользователей (для ветки «нет пользователей»)."""
    async with get_db() as conn:
        await conn.execute("DELETE FROM users")
        await conn.commit()


# ---------------------------------------------------------------------------
# Вход в раздел
# ---------------------------------------------------------------------------


async def test_settings_menu_denied_for_non_full(
    test_db, make_message, fsm_state
):
    msg = make_message(BTN_SETTINGS)
    await hs.settings_menu(msg, fsm_state, role="operator")

    assert await fsm_state.get_state() is None
    assert "нет доступа" in msg.answer.call_args[0][0].lower()


async def test_settings_menu_full(test_db, make_message, fsm_state):
    msg = make_message(BTN_SETTINGS)
    await hs.settings_menu(msg, fsm_state, role="full")

    assert await fsm_state.get_state() == SettingsSection.menu.state
    assert "Настройки" in msg.answer.call_args[0][0]


async def test_settings_back_clears_state(test_db, make_message, fsm_state):
    await fsm_state.set_state(SettingsSection.menu)
    msg = make_message(BTN_BACK)
    await hs.settings_back(msg, fsm_state, role="full")

    assert await fsm_state.get_state() is None
    assert "Главное меню" in msg.answer.call_args[0][0]


# ---------------------------------------------------------------------------
# Пользователи и роли
# ---------------------------------------------------------------------------


async def test_show_users_empty(test_db, make_message, fsm_state):
    await _clear_users()
    msg = make_message(BTN_SET_USERS)
    await hs.users_menu_from_settings(msg, fsm_state)

    assert await fsm_state.get_state() == UsersSection.list.state
    assert (await fsm_state.get_data())["users_map"] == {}
    assert "Нет пользователей" in msg.answer.call_args[0][0]


async def test_show_users_with_admin_and_regular(
    test_db, make_message, fsm_state
):
    """Список: защищённый админ (🔒) + обычный пользователь с именем."""
    await _add_regular_user()
    msg = make_message(BTN_SET_USERS)
    await hs.users_menu_from_settings(msg, fsm_state)

    assert await fsm_state.get_state() == UsersSection.list.state
    mapping = (await fsm_state.get_data())["users_map"]
    assert set(mapping.values()) == {ADMIN_ID, REGULAR_ID}
    text = msg.answer.call_args[0][0]
    assert "🔒" in text
    assert "Bob" in text


async def test_users_back_to_settings(test_db, make_message, fsm_state):
    await fsm_state.set_state(UsersSection.list)
    msg = make_message(BTN_BACK)
    await hs.users_back(msg, fsm_state)

    assert await fsm_state.get_state() == SettingsSection.menu.state


async def test_users_to_defaults(test_db, make_message, fsm_state):
    await fsm_state.set_state(UsersSection.list)
    msg = make_message(BTN_SET_DEFAULTS)
    await hs.users_to_defaults(msg, fsm_state)

    assert await fsm_state.get_state() == DefaultsSection.view.state


async def test_users_pick_unknown_text_ignored(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(UsersSection.list)
    await fsm_state.update_data(users_map={"✅ Some": ADMIN_ID})
    msg = make_message("мимо кнопок")
    await hs.users_pick(msg, fsm_state)

    msg.answer.assert_not_called()
    assert await fsm_state.get_state() == UsersSection.list.state


async def test_users_pick_user_deleted(test_db, make_message, fsm_state):
    """Кнопка указывает на tg_id, которого уже нет в БД."""
    await fsm_state.set_state(UsersSection.list)
    await fsm_state.update_data(users_map={"👻 Ghost": 999999})
    msg = make_message("👻 Ghost")
    await hs.users_pick(msg, fsm_state)

    assert "не найден" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() == UsersSection.list.state


async def test_users_pick_protected_admin(test_db, make_message, fsm_state):
    await fsm_state.set_state(UsersSection.list)
    await fsm_state.update_data(users_map={"✅ Admin 🔒": ADMIN_ID})
    msg = make_message("✅ Admin 🔒")
    await hs.users_pick(msg, fsm_state)

    assert "Защищённый админ" in msg.answer.call_args[0][0]
    assert await fsm_state.get_state() == UsersSection.list.state


async def test_users_pick_regular_opens_role_edit(
    test_db, make_message, fsm_state
):
    await _add_regular_user()
    await fsm_state.set_state(UsersSection.list)
    await fsm_state.update_data(users_map={"⛔ Bob": REGULAR_ID})
    msg = make_message("⛔ Bob")
    await hs.users_pick(msg, fsm_state)

    assert await fsm_state.get_state() == UsersSection.role_edit.state
    assert (await fsm_state.get_data())["target_tg_id"] == REGULAR_ID
    assert "Выберите новую роль" in msg.answer.call_args[0][0]


async def test_role_cancel_returns_to_list(test_db, make_message, fsm_state):
    await fsm_state.set_state(UsersSection.role_edit)
    msg = make_message(BTN_CANCEL_BACK)
    await hs.role_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == UsersSection.list.state


async def test_role_set_without_target_ignored(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(UsersSection.role_edit)
    msg = make_message(BTN_ROLE_OPERATOR)
    await hs.role_set(msg, fsm_state)

    msg.answer.assert_not_called()


async def test_role_set_protected_admin(test_db, make_message, fsm_state):
    await fsm_state.set_state(UsersSection.role_edit)
    await fsm_state.update_data(target_tg_id=ADMIN_ID)
    msg = make_message(BTN_ROLE_OPERATOR)
    await hs.role_set(msg, fsm_state)

    texts = [c.args[0] for c in msg.answer.call_args_list]
    assert any("Защищённый админ" in t for t in texts)
    assert await db_users.get_role(ADMIN_ID) == "full"
    assert await fsm_state.get_state() == UsersSection.list.state


async def test_role_set_regular_user(test_db, make_message, fsm_state):
    await _add_regular_user()
    await fsm_state.set_state(UsersSection.role_edit)
    await fsm_state.update_data(target_tg_id=REGULAR_ID)
    msg = make_message(BTN_ROLE_OPERATOR)
    await hs.role_set(msg, fsm_state)

    assert await db_users.get_role(REGULAR_ID) == "operator"
    texts = [c.args[0] for c in msg.answer.call_args_list]
    assert any("Роль обновлена" in t for t in texts)
    assert await fsm_state.get_state() == UsersSection.list.state


async def test_role_fallback_silent(test_db, make_message):
    msg = make_message("произвольный текст")
    assert await hs.role_fallback(msg) is None
    msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Стандартные тарифы: просмотр и переходы
# ---------------------------------------------------------------------------


def test_period_label_variants():
    assert fmt.period_label(1) == "ежедневный тариф"
    assert fmt.period_label(30) == "ежемесячный тариф"
    assert fmt.period_label(45) == "каждые 45 дн."


async def test_defaults_from_settings(test_db, make_message, fsm_state):
    await fsm_state.set_state(SettingsSection.menu)
    msg = make_message(BTN_SET_DEFAULTS)
    await hs.defaults_from_settings(msg, fsm_state)

    assert await fsm_state.get_state() == DefaultsSection.view.state
    text = msg.answer.call_args[0][0]
    assert "Стандартные тарифы" in text
    assert "ежемесячный тариф" in text  # период 30 из test_db


async def test_defaults_back(test_db, make_message, fsm_state):
    await fsm_state.set_state(DefaultsSection.view)
    msg = make_message(BTN_BACK)
    await hs.defaults_back(msg, fsm_state)

    assert await fsm_state.get_state() == SettingsSection.menu.state


async def test_def_edit_entry_prompts(test_db, make_message, fsm_state):
    msg = make_message(BTN_DEF_ENTRY)
    await hs.def_edit_entry(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == EditDefaultEntry.waiting_for_value.state
    )
    assert "стоимость входа" in msg.answer.call_args[0][0]


async def test_def_edit_free_prompts(test_db, make_message, fsm_state):
    msg = make_message(BTN_DEF_FREE)
    await hs.def_edit_free(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == EditDefaultFreeDays.waiting_for_value.state
    )


async def test_def_edit_storage_rate_prompts(
    test_db, make_message, fsm_state
):
    msg = make_message(BTN_DEF_STORAGE_RATE)
    await hs.def_edit_storage_rate(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == EditDefaultStorageRate.waiting_for_value.state
    )


async def test_def_edit_storage_period_prompts(
    test_db, make_message, fsm_state
):
    msg = make_message(BTN_DEF_STORAGE_PERIOD)
    await hs.def_edit_storage_period(msg, fsm_state)

    assert (
        await fsm_state.get_state()
        == EditDefaultStoragePeriod.waiting_for_value.state
    )


async def test_defaults_fallback_silent(test_db, make_message):
    msg = make_message("мимо")
    assert await hs.defaults_fallback(msg) is None
    msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# FSM ввода значений
# ---------------------------------------------------------------------------


async def test_def_entry_cancel(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultEntry.waiting_for_value)
    msg = make_message(BTN_CANCEL_BACK)
    await hs.def_entry_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == DefaultsSection.view.state


async def test_def_entry_value_invalid(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultEntry.waiting_for_value)
    msg = make_message("abc")
    await hs.def_entry_value(msg, fsm_state)

    assert "Введите число" in msg.answer.call_args[0][0]
    assert await get_setting("default_entry_fee") == 20.0


async def test_def_entry_value_negative_rejected(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(EditDefaultEntry.waiting_for_value)
    msg = make_message("-5")
    await hs.def_entry_value(msg, fsm_state)

    assert await get_setting("default_entry_fee") == 20.0


async def test_def_entry_value_saves_comma_decimal(
    test_db, make_message, fsm_state
):
    """Запятая принимается как десятичный разделитель."""
    await fsm_state.set_state(EditDefaultEntry.waiting_for_value)
    msg = make_message("25,5")
    await hs.def_entry_value(msg, fsm_state)

    assert await get_setting("default_entry_fee") == 25.5
    assert await fsm_state.get_state() == DefaultsSection.view.state


async def test_def_free_cancel(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultFreeDays.waiting_for_value)
    msg = make_message(BTN_CANCEL_BACK)
    await hs.def_free_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == DefaultsSection.view.state


async def test_def_free_value_invalid(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultFreeDays.waiting_for_value)
    msg = make_message("много")
    await hs.def_free_value(msg, fsm_state)

    assert "целое число" in msg.answer.call_args[0][0]
    assert await get_setting("default_free_days") == 30


async def test_def_free_value_negative_rejected(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(EditDefaultFreeDays.waiting_for_value)
    msg = make_message("-1")
    await hs.def_free_value(msg, fsm_state)

    assert await get_setting("default_free_days") == 30


async def test_def_free_value_saves(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultFreeDays.waiting_for_value)
    msg = make_message("10")
    await hs.def_free_value(msg, fsm_state)

    assert await get_setting("default_free_days") == 10.0
    assert await fsm_state.get_state() == DefaultsSection.view.state


async def test_def_rate_cancel(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultStorageRate.waiting_for_value)
    msg = make_message(BTN_CANCEL_BACK)
    await hs.def_rate_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == DefaultsSection.view.state


async def test_def_rate_value_invalid(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultStorageRate.waiting_for_value)
    msg = make_message("дорого")
    await hs.def_rate_value(msg, fsm_state)

    assert await get_setting("default_storage_rate") == 20.0


async def test_def_rate_value_saves(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultStorageRate.waiting_for_value)
    msg = make_message("0.5")
    await hs.def_rate_value(msg, fsm_state)

    assert await get_setting("default_storage_rate") == 0.5
    assert await fsm_state.get_state() == DefaultsSection.view.state


async def test_def_period_cancel(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultStoragePeriod.waiting_for_value)
    msg = make_message(BTN_CANCEL_BACK)
    await hs.def_period_cancel(msg, fsm_state)

    assert await fsm_state.get_state() == DefaultsSection.view.state


async def test_def_period_value_zero_rejected(
    test_db, make_message, fsm_state
):
    """Период < 1 невалиден (деление на период в калькуляторе)."""
    await fsm_state.set_state(EditDefaultStoragePeriod.waiting_for_value)
    msg = make_message("0")
    await hs.def_period_value(msg, fsm_state)

    assert "целое число ≥ 1" in msg.answer.call_args[0][0]
    assert await get_setting("default_storage_period_days") == 30


async def test_def_period_value_invalid_text(
    test_db, make_message, fsm_state
):
    await fsm_state.set_state(EditDefaultStoragePeriod.waiting_for_value)
    msg = make_message("месяц")
    await hs.def_period_value(msg, fsm_state)

    assert await get_setting("default_storage_period_days") == 30


async def test_def_period_value_daily_saves(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultStoragePeriod.waiting_for_value)
    msg = make_message("1")
    await hs.def_period_value(msg, fsm_state)

    assert await get_setting("default_storage_period_days") == 1.0
    texts = [c.args[0] for c in msg.answer.call_args_list]
    assert any("ежедневный тариф" in t for t in texts)
    assert await fsm_state.get_state() == DefaultsSection.view.state


# ---------------------------------------------------------------------------
# Парсеры (краевые случаи, не достижимые через хендлеры)
# ---------------------------------------------------------------------------


def test_parsers_handle_none():
    assert fmt.parse_float(None) is None
    assert fmt.parse_int_nonneg(None) is None
    assert fmt.parse_int_positive(None) is None
    assert fmt.parse_int_nonneg("0") == 0
    assert fmt.parse_int_positive("-3") is None
