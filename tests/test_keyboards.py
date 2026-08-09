"""Тесты keyboards/*: тексты кнопок и структура reply-клавиатур."""
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

from keyboards import companies as kb_comp
from keyboards import containers as kb_cont
from keyboards import main as kb_main
from keyboards import register as kb_reg
from keyboards import reports as kb_rep
from keyboards import settings as kb_set


def _texts(kb: ReplyKeyboardMarkup) -> list[list[str]]:
    """Тексты кнопок построчно."""
    return [[btn.text for btn in row] for row in kb.keyboard]


def _flat(kb: ReplyKeyboardMarkup) -> list[str]:
    return [btn.text for row in kb.keyboard for btn in row]


# ---------------------------------------------------------------------------
# keyboards/main.py
# ---------------------------------------------------------------------------


def test_main_menu_reports_only():
    kb = kb_main.main_menu("reports_only")
    assert _texts(kb) == [[kb_main.BTN_REPORTS]]


def test_main_menu_operator():
    kb = kb_main.main_menu("operator")
    assert _texts(kb) == [[kb_main.BTN_CONTAINERS]]


def test_main_menu_full():
    kb = kb_main.main_menu("full")
    assert _texts(kb) == [
        [kb_main.BTN_CONTAINERS, kb_main.BTN_COMPANIES],
        [kb_main.BTN_REPORTS, kb_main.BTN_SETTINGS],
    ]


def test_remove_kb():
    assert isinstance(kb_main.remove_kb(), ReplyKeyboardRemove)


# ---------------------------------------------------------------------------
# keyboards/companies.py
# ---------------------------------------------------------------------------


def test_companies_list_kb_sorting_and_mapping():
    companies = [
        {"id": 2, "name": "beta", "active_count": None},
        {"id": 1, "name": "Acme", "active_count": 3},
    ]
    kb, mapping = kb_comp.companies_list_reply_kb(companies)

    # Сортировка регистронезависимо, None-счётчик выводится как 0
    assert _flat(kb) == [
        "🏢 Acme (3)",
        "🏢 beta (0)",
        kb_comp.BTN_ADD_COMPANY,
        kb_main.BTN_BACK,
    ]
    assert mapping == {"🏢 Acme (3)": 1, "🏢 beta (0)": 2}


def test_companies_list_kb_empty():
    kb, mapping = kb_comp.companies_list_reply_kb([])
    assert _flat(kb) == [kb_comp.BTN_ADD_COMPANY, kb_main.BTN_BACK]
    assert mapping == {}


def test_company_card_kb():
    assert _flat(kb_comp.company_card_reply_kb()) == [
        kb_comp.BTN_COMPANY_EDIT_ENTRY,
        kb_comp.BTN_COMPANY_EDIT_FREE_DAYS,
        kb_comp.BTN_COMPANY_EDIT_STORAGE_RATE,
        kb_comp.BTN_COMPANY_EDIT_STORAGE_PERIOD,
        kb_comp.BTN_COMPANY_RENAME,
        kb_comp.BTN_COMPANY_DELETE,
        kb_comp.BTN_COMPANIES_BACK,
    ]


def test_company_edit_field_kb():
    assert _flat(kb_comp.company_edit_field_reply_kb()) == [
        kb_comp.BTN_RESET_DEFAULT,
        kb_comp.BTN_CANCEL_X,
    ]


def test_company_rename_kb():
    assert _flat(kb_comp.company_rename_reply_kb()) == [kb_comp.BTN_CANCEL_X]


def test_company_delete_confirm_kb():
    assert _flat(kb_comp.company_delete_confirm_reply_kb()) == [
        kb_comp.BTN_CONFIRM_DELETE,
        kb_comp.BTN_CANCEL_X,
    ]


# ---------------------------------------------------------------------------
# keyboards/containers.py
# ---------------------------------------------------------------------------


def test_containers_menu_kb():
    assert _flat(kb_cont.containers_menu_reply_kb()) == [
        kb_cont.BTN_ADD_CONTAINER,
        kb_cont.BTN_SEARCH_BY_TYPE,
    ]


def test_containers_type_select_kb():
    texts = _texts(kb_cont.containers_type_select_reply_kb())
    assert texts == [
        ["20GP", "20HQ", "40GP"],
        ["40HQ", "45HQ"],
        [kb_main.BTN_BACK],
    ]


def test_container_card_kb_on_terminal():
    assert _flat(kb_cont.container_card_reply_kb("on_terminal")) == [
        kb_cont.BTN_DEPART,
        kb_cont.BTN_CHANGE_NUMBER,
        kb_cont.BTN_CHANGE_TYPE,
        kb_cont.BTN_CHANGE_COMPANY,
        kb_cont.BTN_DELETE,
        kb_cont.BTN_CARD_BACK_ACTIVE,
    ]


def test_container_card_kb_in_transit():
    assert _flat(kb_cont.container_card_reply_kb("in_transit")) == [
        kb_cont.BTN_ARRIVED,
        kb_cont.BTN_CHANGE_COMPANY,
        kb_cont.BTN_DELETE,
        kb_cont.BTN_CARD_BACK_ACTIVE,
    ]


def test_container_card_kb_departed():
    assert _flat(kb_cont.container_card_reply_kb("departed")) == [
        kb_cont.BTN_UNDEPART,
        kb_cont.BTN_EDIT_DEPARTURE_DATE,
        kb_cont.BTN_DELETE,
        kb_cont.BTN_CARD_BACK_ACTIVE,
    ]


def test_container_card_kb_with_history():
    """with_history=True вставляет «📜 История» перед «◀ К списку»."""
    for status in ("on_terminal", "in_transit", "departed"):
        flat = _flat(
            kb_cont.container_card_reply_kb(status, with_history=True)
        )
        assert flat[-2] == kb_cont.BTN_HISTORY
        assert flat[-1] == kb_cont.BTN_CARD_BACK_ACTIVE


def test_depart_date_select_kb():
    assert _flat(kb_cont.depart_date_select_reply_kb()) == [
        kb_cont.BTN_DEPART_TODAY,
        kb_cont.BTN_DEPART_MANUAL,
        kb_cont.BTN_DEPART_CANCEL,
    ]


def test_depart_manual_date_kb():
    assert _flat(kb_cont.depart_manual_date_reply_kb()) == [
        kb_cont.BTN_DEPART_CANCEL,
    ]


def test_type_select_kb():
    texts = _texts(kb_cont.type_select_reply_kb())
    assert texts == [
        ["20GP", "20HQ", "40GP"],
        ["40HQ", "45HQ"],
        [kb_cont.BTN_CANCEL],
    ]


def test_company_select_kb_sorted_with_cancel():
    companies = [{"name": "beta"}, {"name": "Acme"}]
    kb = kb_cont.company_select_reply_kb(companies)
    assert _flat(kb) == ["🏢 Acme", "🏢 beta", kb_cont.BTN_CANCEL]


def test_delete_confirm_kb():
    assert _flat(kb_cont.delete_confirm_reply_kb()) == [
        kb_cont.BTN_CONFIRM_DELETE,
        kb_cont.BTN_CANCEL,
    ]


def test_reserved_button_texts_include_sections():
    """Системные тексты всех разделов присутствуют в стоп-наборе."""
    assert kb_cont.BTN_DEPART in kb_cont.RESERVED_BUTTON_TEXTS
    assert "20GP" in kb_cont.RESERVED_BUTTON_TEXTS
    assert "🏢 По одной компании" in kb_cont.RESERVED_BUTTON_TEXTS
    assert kb_rep.BTN_SCOPE_ALL_CSV in kb_cont.RESERVED_BUTTON_TEXTS
    assert kb_rep.BTN_SCOPE_COMPANY_CSV in kb_cont.RESERVED_BUTTON_TEXTS


# ---------------------------------------------------------------------------
# keyboards/register.py
# ---------------------------------------------------------------------------


def test_register_company_kb_pairs_rows():
    """Чётное число компаний — по две в ряд + отмена."""
    kb = kb_reg.register_company_reply_kb(["Acme", "Beta"])
    assert _texts(kb) == [["Acme", "Beta"], [kb_reg.BTN_REG_CANCEL]]


def test_register_company_kb_odd_tail():
    """Нечётное число — последняя компания в ряду одна."""
    kb = kb_reg.register_company_reply_kb(["Acme", "Beta", "Gamma"])
    assert _texts(kb) == [
        ["Acme", "Beta"],
        ["Gamma"],
        [kb_reg.BTN_REG_CANCEL],
    ]


def test_register_company_kb_empty():
    kb = kb_reg.register_company_reply_kb([])
    assert _texts(kb) == [[kb_reg.BTN_REG_CANCEL]]


def test_register_arrival_date_kb():
    assert _flat(kb_reg.register_arrival_date_reply_kb()) == [
        kb_reg.BTN_ARRIVAL_TODAY,
        kb_reg.BTN_ARRIVAL_TRANSIT,
        kb_reg.BTN_ARRIVAL_MANUAL,
        kb_reg.BTN_REG_CANCEL,
    ]


def test_register_manual_date_kb():
    assert _flat(kb_reg.register_manual_date_reply_kb()) == [
        kb_reg.BTN_REG_CANCEL,
    ]


def test_register_type_kb():
    texts = _texts(kb_reg.register_type_reply_kb())
    assert texts == [
        ["20GP", "20HQ", "40GP"],
        ["40HQ", "45HQ"],
        [kb_reg.BTN_REG_SKIP_TYPE],
        [kb_reg.BTN_REG_CANCEL],
    ]


# ---------------------------------------------------------------------------
# keyboards/reports.py
# ---------------------------------------------------------------------------


def test_reports_type_kb():
    assert _flat(kb_rep.reports_type_reply_kb()) == [
        kb_rep.BTN_REP_ACTIVE,
        kb_rep.BTN_REP_MIXED,
        kb_rep.BTN_REP_DEPARTED,
        kb_main.BTN_BACK,
    ]


def test_reports_scope_kb():
    assert _flat(kb_rep.reports_scope_reply_kb()) == [
        kb_rep.BTN_SCOPE_ALL,
        kb_rep.BTN_SCOPE_COMPANY,
        kb_rep.BTN_SCOPE_ALL_CSV,
        kb_rep.BTN_SCOPE_COMPANY_CSV,
        kb_main.BTN_BACK,
    ]


def test_report_company_select_kb_sorted():
    companies = [{"name": "beta"}, {"name": "Acme"}]
    kb = kb_rep.report_company_select_reply_kb(companies)
    assert _flat(kb) == ["🏢 Acme", "🏢 beta", kb_main.BTN_BACK]


# ---------------------------------------------------------------------------
# keyboards/settings.py
# ---------------------------------------------------------------------------


def test_settings_kb():
    assert _texts(kb_set.settings_reply_kb()) == [
        [kb_set.BTN_SET_USERS, kb_set.BTN_SET_DEFAULTS],
        [kb_main.BTN_BACK],
    ]


def test_user_button_text_variants():
    admin_ids = frozenset({1})
    # Полное имя + замок у защищённого админа
    admin = {"tg_id": 1, "role": "full", "full_name": "Admin", "username": "adm"}
    assert kb_set._user_button_text(admin, admin_ids) == "✅ Admin 🔒"
    # Без full_name — @username
    by_username = {
        "tg_id": 2, "role": "reports_only", "full_name": None, "username": "rep",
    }
    assert kb_set._user_button_text(by_username, admin_ids) == "📊 @rep"
    # Без имени и username — tg_id; неизвестная роль — «❓»
    bare = {"tg_id": 3, "role": "ghost", "full_name": None, "username": None}
    assert kb_set._user_button_text(bare, admin_ids) == "❓ 3"


def test_users_list_kb_mapping():
    users = [
        {"tg_id": 1, "role": "full", "full_name": "Admin", "username": None},
        {"tg_id": 2, "role": "none", "full_name": None, "username": "guest"},
    ]
    kb, mapping = kb_set.users_list_reply_kb(users, frozenset({1}))

    assert mapping == {"✅ Admin 🔒": 1, "⛔ @guest": 2}
    assert _flat(kb) == [
        "✅ Admin 🔒",
        "⛔ @guest",
        kb_set.BTN_SET_DEFAULTS,
        kb_main.BTN_BACK,
    ]


def test_user_role_kb():
    assert _flat(kb_set.user_role_reply_kb()) == [
        kb_set.BTN_ROLE_FULL,
        kb_set.BTN_ROLE_OPERATOR,
        kb_set.BTN_ROLE_REPORTS,
        kb_set.BTN_ROLE_NONE,
        kb_set.BTN_CANCEL_BACK,
    ]


def test_defaults_kb():
    assert _flat(kb_set.defaults_reply_kb()) == [
        kb_set.BTN_DEF_ENTRY,
        kb_set.BTN_DEF_FREE,
        kb_set.BTN_DEF_STORAGE_RATE,
        kb_set.BTN_DEF_STORAGE_PERIOD,
        kb_main.BTN_BACK,
    ]


def test_default_edit_kb():
    assert _flat(kb_set.default_edit_reply_kb()) == [kb_set.BTN_CANCEL_BACK]
