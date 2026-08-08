"""Дополнительные тесты DB-слоя: ветки, не покрытые test_db.py."""
from db import companies as db_comp, containers as db_cont, users as db_users


# --- Companies ---


async def test_list_companies_with_active_counts(test_db):
    """Счётчик активных контейнеров по компаниям, сортировка по имени."""
    alpha = await db_comp.add_company("Alpha")
    await db_comp.add_company("Beta")
    await db_cont.add_container("AAAA0000001", "AAAA 0000001", alpha, "on_terminal", "2026-01-01")
    await db_cont.add_container("AAAA0000002", "AAAA 0000002", alpha, "in_transit", None)
    await db_cont.add_container("AAAA0000003", "AAAA 0000003", alpha, "departed", "2026-01-01")

    rows = await db_comp.list_companies_with_active_counts()
    assert [(r["name"], r["active_count"]) for r in rows] == [
        ("Alpha", 2),  # departed не считается активным
        ("Beta", 0),
    ]


async def test_update_free_days(test_db):
    cid = await db_comp.add_company("DaysCo")
    await db_comp.update_free_days(cid, 15)
    assert (await db_comp.get_company(cid))["free_days"] == 15
    # Сброс на стандартный (NULL)
    await db_comp.update_free_days(cid, None)
    assert (await db_comp.get_company(cid))["free_days"] is None


async def test_update_storage_rate(test_db):
    cid = await db_comp.add_company("RateCo")
    await db_comp.update_storage_rate(cid, 7.5)
    assert (await db_comp.get_company(cid))["storage_rate"] == 7.5


async def test_update_storage_period_days(test_db):
    cid = await db_comp.add_company("PeriodCo")
    await db_comp.update_storage_period_days(cid, 1)
    assert (await db_comp.get_company(cid))["storage_period_days"] == 1


# --- Containers ---


async def test_add_container_duplicate_returns_none(test_db):
    """Дубликат номера при INSERT возвращает None."""
    cid = await db_comp.add_company("Co")
    first = await db_cont.add_container("DUPL0000001", "DUPL 0000001", cid, "on_terminal", "2026-01-01")
    assert first is not None
    dup = await db_cont.add_container("DUPL0000001", "DUPL 0000001", cid, "on_terminal", "2026-01-01")
    assert dup is None


async def test_list_departed_pagination(test_db):
    cid = await db_comp.add_company("Co")
    for i in range(3):
        cont_id = await db_cont.add_container(
            f"DEPP{i:07d}", f"DEPP {i:07d}", cid, "on_terminal", "2026-01-01"
        )
        await db_cont.set_departed(cont_id, f"2026-02-{i+1:02d} 10:00:00")

    rows, total = await db_cont.list_departed(page=1, per_page=2)
    assert total == 3
    assert len(rows) == 2
    # Сортировка по дате вывоза по убыванию
    assert rows[0]["departure_date"] > rows[1]["departure_date"]
    rows2, _ = await db_cont.list_departed(page=2, per_page=2)
    assert len(rows2) == 1


async def test_set_arrived(test_db):
    """in_transit → on_terminal с проставленной датой прибытия."""
    cid = await db_comp.add_company("Co")
    cont_id = await db_cont.add_container("TRNS0000001", "TRNS 0000001", cid, "in_transit", None)
    await db_cont.set_arrived(cont_id)
    cont = await db_cont.get_container(cont_id)
    assert cont["status"] == "on_terminal"
    assert cont["arrival_date"] is not None


async def test_set_departed_default_date(test_db):
    """Без явной даты вывоза подставляется текущий момент."""
    cid = await db_comp.add_company("Co")
    cont_id = await db_cont.add_container("NOWW0000001", "NOWW 0000001", cid, "on_terminal", "2026-01-01")
    await db_cont.set_departed(cont_id)
    cont = await db_cont.get_container(cont_id)
    assert cont["status"] == "departed"
    assert cont["departure_date"] is not None


async def test_update_departure_date(test_db):
    """Правка даты вывоза не меняет статус."""
    cid = await db_comp.add_company("Co")
    cont_id = await db_cont.add_container("EDIT0000001", "EDIT 0000001", cid, "on_terminal", "2026-01-01")
    await db_cont.set_departed(cont_id, "2026-02-01 10:00:00")
    await db_cont.update_departure_date(cont_id, "2026-02-05 12:00:00")
    cont = await db_cont.get_container(cont_id)
    assert cont["departure_date"] == "2026-02-05 12:00:00"
    assert cont["status"] == "departed"


async def test_update_type(test_db):
    cid = await db_comp.add_company("Co")
    cont_id = await db_cont.add_container("TYPE0000001", "TYPE 0000001", cid, "on_terminal", "2026-01-01", "20ft")
    await db_cont.update_type(cont_id, "40ft")
    assert (await db_cont.get_container(cont_id))["type"] == "40ft"


async def test_update_company(test_db):
    cid1 = await db_comp.add_company("From")
    cid2 = await db_comp.add_company("To")
    cont_id = await db_cont.add_container("MOVE0000001", "MOVE 0000001", cid1, "on_terminal", "2026-01-01")
    await db_cont.update_company(cont_id, cid2)
    cont = await db_cont.get_container(cont_id)
    assert cont["company_id"] == cid2
    assert cont["company_name"] == "To"


async def test_active_by_type(test_db):
    """Только on_terminal заданного типа, in_transit и другие типы — мимо."""
    cid = await db_comp.add_company("Co")
    await db_cont.add_container("TYPA0000001", "TYPA 0000001", cid, "on_terminal", "2026-01-01", "20ft")
    await db_cont.add_container("TYPA0000002", "TYPA 0000002", cid, "in_transit", None, "20ft")
    await db_cont.add_container("TYPA0000003", "TYPA 0000003", cid, "on_terminal", "2026-01-01", "40ft")

    rows = await db_cont.active_by_type("20ft")
    assert [r["display_number"] for r in rows] == ["TYPA 0000001"]
    assert rows[0]["company_name"] == "Co"


async def test_active_for_company(test_db):
    """on_terminal + in_transit компании, без departed и чужих."""
    cid = await db_comp.add_company("Mine")
    other = await db_comp.add_company("Other")
    await db_cont.add_container("ACTV0000001", "ACTV 0000001", cid, "on_terminal", "2026-01-02")
    await db_cont.add_container("ACTV0000002", "ACTV 0000002", cid, "in_transit", None)
    await db_cont.add_container("ACTV0000003", "ACTV 0000003", cid, "departed", "2026-01-01")
    await db_cont.add_container("ACTV0000004", "ACTV 0000004", other, "on_terminal", "2026-01-01")

    rows = await db_cont.active_for_company(cid)
    assert {r["number"] for r in rows} == {"ACTV0000001", "ACTV0000002"}


async def test_all_for_company(test_db):
    """Все контейнеры компании независимо от статуса."""
    cid = await db_comp.add_company("AllCo")
    await db_cont.add_container("ALLC0000001", "ALLC 0000001", cid, "on_terminal", "2026-01-02")
    await db_cont.add_container("ALLC0000002", "ALLC 0000002", cid, "departed", "2026-01-01")

    rows = await db_cont.all_for_company(cid)
    assert len(rows) == 2
    assert all(r["company_name"] == "AllCo" for r in rows)


async def test_departed_for_company(test_db):
    cid = await db_comp.add_company("DepCo")
    await db_cont.add_container("DEPC0000001", "DEPC 0000001", cid, "on_terminal", "2026-01-01")
    c2 = await db_cont.add_container("DEPC0000002", "DEPC 0000002", cid, "on_terminal", "2026-01-01")
    await db_cont.set_departed(c2, "2026-02-01 10:00:00")

    rows = await db_cont.departed_for_company(cid)
    assert [r["number"] for r in rows] == ["DEPC0000002"]


async def test_all_containers(test_db):
    """Полная выборка с джойном компании для общего отчёта."""
    cid = await db_comp.add_company("RepCo")
    await db_cont.add_container("REPO0000001", "REPO 0000001", cid, "on_terminal", "2026-01-01")
    await db_cont.add_container("REPO0000002", "REPO 0000002", cid, "departed", "2026-01-01")

    rows = await db_cont.all_containers()
    assert len(rows) == 2
    assert rows[0]["company_name"] == "RepCo"


async def test_fetch_for_report_empty_statuses(test_db):
    """Пустой кортеж статусов — пустая выдача без запроса."""
    assert await db_cont.fetch_for_report(()) == []


async def test_fetch_for_report_filters(test_db):
    """Фильтрация по статусам и по компании."""
    cid1 = await db_comp.add_company("R1")
    cid2 = await db_comp.add_company("R2")
    await db_cont.add_container("FREP0000001", "FREP 0000001", cid1, "on_terminal", "2026-01-01")
    await db_cont.add_container("FREP0000002", "FREP 0000002", cid1, "departed", "2026-01-01")
    await db_cont.add_container("FREP0000003", "FREP 0000003", cid2, "on_terminal", "2026-01-01")

    rows = await db_cont.fetch_for_report(("on_terminal",))
    assert {r["number"] for r in rows} == {"FREP0000001", "FREP0000003"}

    rows = await db_cont.fetch_for_report(
        ("on_terminal", "departed"), company_id=cid1
    )
    assert {r["number"] for r in rows} == {"FREP0000001", "FREP0000002"}


# --- Users ---


async def test_get_user(test_db):
    """get_user возвращает запись админа из init_db и None для чужого id."""
    user = await db_users.get_user(111111)
    assert user is not None
    assert user["role"] == "full"
    assert await db_users.get_user(424242) is None


async def test_upsert_existing_user_promoted_to_admin(test_db):
    """Существующий не-full пользователь из ADMIN_IDS повышается до full."""
    role = await db_users.upsert_user(777777, "u", "User", frozenset())
    assert role == "none"
    role = await db_users.upsert_user(777777, "u2", "User2", frozenset({777777}))
    assert role == "full"
    user = await db_users.get_user(777777)
    assert user["role"] == "full"
    assert user["username"] == "u2"


async def test_init_db_creates_parent_directory(tmp_path):
    """init_db создаёт несуществующий каталог БД (первый запуск вне Docker)."""
    from db import init_db

    db_path = tmp_path / "nested" / "dir" / "fresh.db"
    await init_db(
        path=str(db_path),
        admin_ids=frozenset(),
        default_entry_fee=20.0,
        default_free_days=30,
        default_storage_rate=20.0,
        default_storage_period_days=30,
    )
    assert db_path.exists()
