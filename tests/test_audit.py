"""Тесты аудит-лога: db/audit.py, хуки в хендлерах, просмотр истории.

Ключевые гарантии:
- запись аудита никогда не роняет бизнес-операцию;
- каждая мутирующая операция оставляет читаемый след «кто, когда, что»;
- история в карточке доступна только роли full.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import aiosqlite
import pytest

from db import audit as db_audit
from db import companies as db_comp
from db import containers as db_cont
from db import users as db_users
from db.settings import get_setting
from handlers import companies as hcomp
from handlers import containers as hc
from handlers import register as hreg
from handlers import settings as hs
from keyboards.containers import (
    BTN_ARRIVED,
    BTN_CONFIRM_DELETE,
    BTN_DEPART_TODAY,
    BTN_HISTORY,
    BTN_UNDEPART,
)
from keyboards.settings import BTN_ROLE_OPERATOR
from states import (
    CompaniesSection,
    ContainerDepart,
    ContainerSection,
    EditCompanyEntry,
    EditCompanyName,
    EditDefaultStorageRate,
    RegisterContainer,
    UsersSection,
)

ARRIVAL = "2026-06-01 10:00:00"


async def _audit_rows(db_path: str) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute("SELECT * FROM audit_log ORDER BY id")
        ).fetchall()


async def _seed_container(
    number: str = "AAAU1111111",
    display: str = "AAAU 1111111",
    status: str = "on_terminal",
    arrival: str | None = ARRIVAL,
    company_id: int | None = None,
    ctype: str | None = "40HQ",
) -> int:
    return await db_cont.add_container(
        number=number,
        display_number=display,
        company_id=company_id,
        status=status,
        arrival_date=arrival,
        container_type=ctype,
    )


# ---------------------------------------------------------------------------
# db/audit.py: actor_name_from
# ---------------------------------------------------------------------------


def test_actor_name_none():
    assert db_audit.actor_name_from(None) == "?"


def test_actor_name_full_name():
    user = SimpleNamespace(id=1, username="bob", full_name="Bob Smith")
    assert db_audit.actor_name_from(user) == "Bob Smith"


def test_actor_name_username_fallback():
    user = SimpleNamespace(id=1, username="bob", full_name=None)
    assert db_audit.actor_name_from(user) == "@bob"


def test_actor_name_id_fallback():
    user = SimpleNamespace(id=42, username=None, full_name=None)
    assert db_audit.actor_name_from(user) == "42"


# ---------------------------------------------------------------------------
# db/audit.py: add_entry / list_for_container
# ---------------------------------------------------------------------------


async def test_add_entry_roundtrip(test_db):
    actor = SimpleNamespace(id=7, username=None, full_name="Ann")
    await db_audit.add_entry(
        actor, "регистрация", "container", 5, "TEMU 1234567",
        "компания: Ромашка",
    )
    rows = await _audit_rows(test_db)
    assert len(rows) == 1
    r = rows[0]
    assert r["actor_tg_id"] == 7
    assert r["actor_name"] == "Ann"
    assert r["action"] == "регистрация"
    assert r["entity_type"] == "container"
    assert r["entity_id"] == 5
    assert r["entity_label"] == "TEMU 1234567"
    assert r["details"] == "компания: Ромашка"
    # created_at в формате проекта
    datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")


async def test_add_entry_actor_none(test_db):
    await db_audit.add_entry(None, "удалён", "container", 1, "X")
    rows = await _audit_rows(test_db)
    assert rows[0]["actor_tg_id"] is None
    assert rows[0]["actor_name"] == "?"


async def test_add_entry_failure_swallowed(test_db, monkeypatch, caplog):
    """Сбой записи аудита логируется и не пробрасывается."""
    def _boom():
        raise RuntimeError("db is gone")

    monkeypatch.setattr(db_audit, "get_db", _boom)
    await db_audit.add_entry(None, "вывезен", "container", 1, "X")
    assert "Сбой записи аудита" in caplog.text
    monkeypatch.undo()
    assert await _audit_rows(test_db) == []


async def test_list_for_container_order_and_limit(test_db):
    cid = await _seed_container()
    other = await _seed_container(
        number="BBBU2222222", display="BBBU 2222222"
    )
    for i in range(20):
        await db_audit.add_entry(
            None, f"действие {i}", "container", cid, "AAAU 1111111"
        )
    # Чужие записи не попадают в выдачу
    await db_audit.add_entry(None, "чужое", "container", other, "BBBU 2222222")
    await db_audit.add_entry(None, "компания", "company", cid, "Ромашка")

    entries = await db_audit.list_for_container("AAAU1111111")
    assert len(entries) == 15
    # Новые сверху
    assert entries[0]["action"] == "действие 19"
    assert entries[-1]["action"] == "действие 5"

    short = await db_audit.list_for_container("AAAU1111111", limit=3)
    assert [e["action"] for e in short] == [
        "действие 19", "действие 18", "действие 17"
    ]


async def test_list_for_container_unknown_number(test_db):
    assert await db_audit.list_for_container("ZZZU0000000") == []


# ---------------------------------------------------------------------------
# Хук: регистрация контейнера
# ---------------------------------------------------------------------------


async def test_registration_writes_audit(test_db, make_message, fsm_state):
    company_id = await db_comp.add_company(name="Ромашка")
    await fsm_state.set_state(RegisterContainer.waiting_for_arrival_date)
    await fsm_state.set_data({
        "number": "CASS1234567",
        "display_number": "CASS 1234567",
        "company_id": company_id,
        "company_name": "Ромашка",
        "container_type": "40HQ",
    })
    await hreg.arrival_today(make_message(), fsm_state, role="full")

    rows = await _audit_rows(test_db)
    assert len(rows) == 1
    r = rows[0]
    assert r["action"] == "регистрация"
    assert r["entity_type"] == "container"
    assert r["entity_label"] == "CASS 1234567"
    assert r["actor_tg_id"] == 111111
    assert r["actor_name"] == "Operator"
    assert "компания: Ромашка" in r["details"]
    assert "тип: 40HQ" in r["details"]
    assert "статус: на терминале" in r["details"]


async def test_registration_transit_audit_details(
    test_db, make_message, fsm_state
):
    """Ветка «в пути» и тип «—» в details."""
    company_id = await db_comp.add_company(name="Ромашка")
    await fsm_state.set_state(RegisterContainer.waiting_for_arrival_date)
    await fsm_state.set_data({
        "number": "CASS1234567",
        "display_number": "CASS 1234567",
        "company_id": company_id,
        "company_name": "Ромашка",
        "container_type": None,
    })
    await hreg.arrival_transit(make_message(), fsm_state, role="full")

    (r,) = await _audit_rows(test_db)
    assert "тип: —" in r["details"]
    assert "статус: в пути" in r["details"]


async def test_registration_duplicate_no_audit(
    test_db, make_message, fsm_state
):
    """Дубликат номера — операции не было, аудит не пишется."""
    company_id = await db_comp.add_company(name="Ромашка")
    await _seed_container(
        number="CASS1234567", display="CASS 1234567", company_id=company_id
    )
    await fsm_state.set_state(RegisterContainer.waiting_for_arrival_date)
    await fsm_state.set_data({
        "number": "CASS1234567",
        "display_number": "CASS 1234567",
        "company_id": company_id,
        "company_name": "Ромашка",
        "container_type": None,
    })
    await hreg.arrival_today(make_message(), fsm_state, role="full")
    assert await _audit_rows(test_db) == []


# ---------------------------------------------------------------------------
# Хуки: операции с контейнером
# ---------------------------------------------------------------------------


async def test_arrived_writes_audit(test_db, make_message, fsm_state):
    cid = await _seed_container(status="in_transit", arrival=None)
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    await hc.card_arrived(make_message(BTN_ARRIVED), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "прибыл на терминал"
    assert r["entity_id"] == cid
    assert r["entity_label"] == "AAAU 1111111"
    assert "дата прибытия:" in r["details"]


async def test_depart_today_writes_audit(test_db, make_message, fsm_state):
    arr = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    cid = await _seed_container(arrival=arr)
    await fsm_state.set_state(ContainerDepart.waiting_for_departure_date)
    await fsm_state.set_data(
        {"container_id": cid, "card_source": "active", "depart_mode": "depart"}
    )
    await hc.depart_today(make_message(BTN_DEPART_TODAY), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "вывезен"
    assert r["details"] == (
        f"дата вывоза: {datetime.now().strftime('%d.%m.%Y')}"
    )


async def test_edit_departure_date_writes_audit(
    test_db, make_message, fsm_state
):
    cid = await _seed_container()
    await db_cont.set_departed(cid, "2026-06-05 12:00:00")
    await fsm_state.set_data(
        {"container_id": cid, "card_source": "departed", "depart_mode": "edit"}
    )
    dep = datetime.now() - timedelta(days=1)
    await hc.depart_manual_input(make_message(dep.strftime("%d.%m.%Y")), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "изменена дата вывоза"
    assert r["details"] == (
        f"дата вывоза: 05.06.2026 → {dep.strftime('%d.%m.%Y')}"
    )


async def test_undepart_writes_audit(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await db_cont.set_departed(cid, "2026-06-05 12:00:00")
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": cid, "card_source": "departed"})
    await hc.card_undepart(make_message(BTN_UNDEPART), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "отменён вывоз"
    assert r["details"] == "снята дата вывоза: 05.06.2026"


async def test_change_type_writes_audit(test_db, make_message, fsm_state):
    cid = await _seed_container(ctype="20GP")
    await fsm_state.set_state(ContainerSection.choosing_type)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    await hc.type_selected(make_message("45HQ"), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "изменён тип"
    assert r["details"] == "тип: 20GP → 45HQ"


async def test_change_company_writes_audit(test_db, make_message, fsm_state):
    await db_comp.add_company(name="Ромашка")
    cid = await _seed_container()
    await fsm_state.set_state(ContainerSection.choosing_company)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    await hc.company_selected(make_message("🏢 Ромашка"), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "сменена компания"
    assert r["details"] == "компания: — → Ромашка"


async def test_change_number_writes_audit(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    await hc.edit_number_process(make_message("ZZZU 9999999"), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "изменён номер"
    assert r["entity_label"] == "ZZZU 9999999"
    assert r["details"] == "номер: AAAU 1111111 → ZZZU 9999999"
    # История доступна по новому номеру
    entries = await db_audit.list_for_container("ZZZU9999999")
    assert len(entries) == 1


async def test_delete_container_writes_audit(test_db, make_message, fsm_state):
    comp_id = await db_comp.add_company(name="Ромашка")
    cid = await _seed_container(company_id=comp_id)
    await fsm_state.set_state(ContainerSection.confirming_delete)
    await fsm_state.set_data({"container_id": cid})
    await hc.delete_confirm(make_message(BTN_CONFIRM_DELETE), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "удалён"
    # Лог читается и после удаления сущности
    assert r["entity_label"] == "AAAU 1111111"
    assert r["details"] == "компания: Ромашка"


# ---------------------------------------------------------------------------
# Хуки: компании
# ---------------------------------------------------------------------------


async def test_company_create_writes_audit(test_db, make_message, fsm_state):
    await fsm_state.set_state(CompaniesSection.adding_name)
    await hcomp.companies_add_process(make_message("Ромашка"), fsm_state)

    rows = await _audit_rows(test_db)
    assert rows[0]["action"] == "создана компания"
    assert rows[0]["entity_type"] == "company"
    assert rows[0]["entity_label"] == "Ромашка"
    assert rows[0]["details"] is None


async def test_company_rename_writes_audit(test_db, make_message, fsm_state):
    comp_id = await db_comp.add_company(name="Старое")
    await fsm_state.set_state(EditCompanyName.waiting_for_name)
    await fsm_state.set_data({"company_id": comp_id})
    await hcomp.rename_process(make_message("Новое"), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "переименована компания"
    assert r["entity_label"] == "Новое"
    assert r["details"] == "название: Старое → Новое"


async def test_company_tariff_value_writes_audit(
    test_db, make_message, fsm_state
):
    comp_id = await db_comp.add_company(name="Ромашка")
    await fsm_state.set_state(EditCompanyEntry.waiting_for_value)
    await fsm_state.set_data({"company_id": comp_id})
    await hcomp.edit_entry_value(make_message("55"), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "изменён тариф"
    assert r["entity_label"] == "Ромашка"
    assert r["details"] == "стоимость входа: стандарт → 55.0"
    assert (await db_comp.get_company(comp_id))["entry_fee"] == 55.0


async def test_company_tariff_reset_writes_audit(
    test_db, make_message, fsm_state
):
    comp_id = await db_comp.add_company(name="Ромашка", entry_fee=50.0)
    await fsm_state.set_state(EditCompanyEntry.waiting_for_value)
    await fsm_state.set_data({"company_id": comp_id})
    await hcomp.edit_entry_reset(make_message(), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["details"] == "стоимость входа: 50.0 → стандарт"
    assert (await db_comp.get_company(comp_id))["entry_fee"] is None


async def test_company_delete_writes_audit(test_db, make_message, fsm_state):
    comp_id = await db_comp.add_company(name="Ромашка")
    await fsm_state.set_state(CompaniesSection.confirming_delete)
    await fsm_state.set_data({"company_id": comp_id})
    await hcomp.delete_confirm(make_message(BTN_CONFIRM_DELETE), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "удалена компания"
    assert r["entity_label"] == "Ромашка"
    assert await db_comp.get_company(comp_id) is None


# ---------------------------------------------------------------------------
# Хуки: настройки
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_cfg(monkeypatch):
    """Фиксирует admin_ids независимо от локального .env."""
    monkeypatch.setattr(
        hs, "_cfg", SimpleNamespace(admin_ids=frozenset({111111}))
    )


async def test_role_change_writes_audit(
    test_db, make_message, fsm_state, patched_cfg
):
    await db_users.upsert_user(
        tg_id=222222, username="bob", full_name="Bob",
        admin_ids=frozenset(),
    )
    await fsm_state.set_state(UsersSection.role_edit)
    await fsm_state.update_data(target_tg_id=222222)
    await hs.role_set(make_message(BTN_ROLE_OPERATOR), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "изменена роль"
    assert r["entity_type"] == "user"
    assert r["entity_id"] == 222222
    assert r["entity_label"] == "Bob"
    assert r["details"] == "роль: Нет доступа → Оператор"


async def test_default_tariff_writes_audit(test_db, make_message, fsm_state):
    await fsm_state.set_state(EditDefaultStorageRate.waiting_for_value)
    await hs.def_rate_value(make_message("35"), fsm_state)

    (r,) = await _audit_rows(test_db)
    assert r["action"] == "изменён стандартный тариф"
    assert r["entity_type"] == "settings"
    assert r["entity_id"] is None
    assert r["entity_label"] == "default_storage_rate"
    assert r["details"] == "ставка хранения: 20.0 → 35.0"
    assert await get_setting("default_storage_rate") == 35.0


# ---------------------------------------------------------------------------
# Прод-безопасность: сбой аудита не ломает операцию
# ---------------------------------------------------------------------------


async def test_audit_failure_does_not_break_operation(
    test_db, make_message, fsm_state, monkeypatch, caplog
):
    """Аудит упал (например, таблицы нет) — вывоз всё равно проходит."""
    def _boom():
        raise RuntimeError("audit storage down")

    monkeypatch.setattr(db_audit, "get_db", _boom)

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
    assert "вывезен" in msg.answer.call_args_list[0].args[0]
    assert "Сбой записи аудита" in caplog.text


# ---------------------------------------------------------------------------
# Просмотр истории в карточке
# ---------------------------------------------------------------------------


async def test_card_history_shows_entries(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await db_audit.add_entry(
        SimpleNamespace(id=1, username=None, full_name="Ann"),
        "регистрация", "container", cid, "AAAU 1111111",
        "компания: Ромашка, тип: 40HQ, статус: на терминале",
    )
    # Запись без details и без имени — ветки «без подробностей» и «?»
    await db_audit.add_entry(
        None, "прибыл на терминал", "container", cid, "AAAU 1111111"
    )
    await fsm_state.set_state(ContainerSection.card)
    await fsm_state.set_data({"container_id": cid, "card_source": "active"})
    msg = make_message(BTN_HISTORY)
    await hc.card_history(msg, fsm_state, role="full")

    text = msg.answer.call_args[0][0]
    assert "История контейнера AAAU 1111111" in text
    assert "Ann: регистрация" in text
    assert "компания: Ромашка" in text
    assert "?: прибыл на терминал" in text
    # Новые сверху
    assert text.index("прибыл на терминал") < text.index("регистрация")


async def test_card_history_empty(test_db, make_message, fsm_state):
    cid = await _seed_container()
    await fsm_state.set_data({"container_id": cid})
    msg = make_message(BTN_HISTORY)
    await hc.card_history(msg, fsm_state, role="full")
    assert "пуста" in msg.answer.call_args[0][0]


async def test_card_history_denied_for_operator(
    test_db, make_message, fsm_state
):
    cid = await _seed_container()
    await fsm_state.set_data({"container_id": cid})
    for role in ("operator", "reports_only"):
        msg = make_message(BTN_HISTORY)
        await hc.card_history(msg, fsm_state, role=role)
        msg.answer.assert_not_called()


async def test_card_history_no_container_id(test_db, make_message, fsm_state):
    msg = make_message(BTN_HISTORY)
    await hc.card_history(msg, fsm_state, role="full")
    msg.answer.assert_not_called()


async def test_card_history_missing_container(
    test_db, make_message, fsm_state
):
    await fsm_state.set_data({"container_id": 999})
    msg = make_message(BTN_HISTORY)
    await hc.card_history(msg, fsm_state, role="full")
    msg.answer.assert_not_called()
