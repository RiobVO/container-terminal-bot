"""Тесты DB-слоя: companies, containers, users, settings."""
import pytest

from db import companies as db_comp, containers as db_cont, users as db_users, settings as db_settings


# --- Companies ---


async def test_add_and_get_company(test_db):
    """Создание компании и получение по id."""
    cid = await db_comp.add_company("TestCo")
    company = await db_comp.get_company(cid)
    assert company["name"] == "TestCo"
    assert company["entry_fee"] is None  # без кастомного тарифа


async def test_add_company_with_custom_tariff(test_db):
    """Компания с кастомными тарифами."""
    cid = await db_comp.add_company("Custom", entry_fee=50.0, free_days=10, storage_rate=5.0, storage_period_days=7)
    company = await db_comp.get_company(cid)
    assert company["entry_fee"] == 50.0
    assert company["free_days"] == 10
    assert company["storage_rate"] == 5.0
    assert company["storage_period_days"] == 7


async def test_list_companies(test_db):
    """Список компаний отсортирован по имени."""
    await db_comp.add_company("Zeta")
    await db_comp.add_company("Alpha")
    companies = await db_comp.list_companies()
    names = [c["name"] for c in companies]
    assert names == ["Alpha", "Zeta"]


async def test_get_company_by_name_ci(test_db):
    """Регистронезависимый поиск."""
    await db_comp.add_company("Maersk")
    result = await db_comp.get_company_by_name_ci("maersk")
    assert result is not None
    assert result["name"] == "Maersk"


async def test_rename_company(test_db):
    cid = await db_comp.add_company("OldName")
    await db_comp.rename_company(cid, "NewName")
    company = await db_comp.get_company(cid)
    assert company["name"] == "NewName"


async def test_delete_company(test_db):
    cid = await db_comp.add_company("ToDelete")
    await db_comp.delete_company(cid)
    assert await db_comp.get_company(cid) is None


async def test_count_total_containers(test_db):
    """Подсчёт всех контейнеров компании."""
    cid = await db_comp.add_company("CountCo")
    await db_cont.add_container("CNTA0000001", "CNTA 0000001", cid, "on_terminal", "2026-01-01")
    await db_cont.add_container("CNTA0000002", "CNTA 0000002", cid, "departed", "2026-01-01")
    assert await db_comp.count_total_containers(cid) == 2


async def test_update_entry_fee(test_db):
    """Обновление стоимости входа."""
    cid = await db_comp.add_company("FeeCo")
    await db_comp.update_entry_fee(cid, 99.0)
    company = await db_comp.get_company(cid)
    assert company["entry_fee"] == 99.0
    # Сброс на стандартный (NULL)
    await db_comp.update_entry_fee(cid, None)
    company = await db_comp.get_company(cid)
    assert company["entry_fee"] is None


# --- Containers ---


async def test_add_and_get_container(test_db):
    """Создание контейнера и получение с JOIN компании."""
    cid = await db_comp.add_company("ShipCo")
    cont_id = await db_cont.add_container("TEMU1234567", "TEMU 1234567", cid, "on_terminal", "2026-01-15 10:00:00", "40ft")
    cont = await db_cont.get_container(cont_id)
    assert cont["number"] == "TEMU1234567"
    assert cont["display_number"] == "TEMU 1234567"
    assert cont["company_name"] == "ShipCo"
    assert cont["status"] == "on_terminal"
    assert cont["type"] == "40ft"


async def test_find_by_number(test_db):
    cid = await db_comp.add_company("Co")
    await db_cont.add_container("MSCU7654321", "MSCU 7654321", cid, "on_terminal", "2026-01-01")
    found = await db_cont.find_by_number("MSCU7654321")
    assert found is not None
    assert found["display_number"] == "MSCU 7654321"
    # Не найден
    assert await db_cont.find_by_number("XXXX0000000") is None


async def test_set_departed_and_undo(test_db):
    cid = await db_comp.add_company("Co")
    cont_id = await db_cont.add_container("ABCD1111111", "ABCD 1111111", cid, "on_terminal", "2026-01-01")
    await db_cont.set_departed(cont_id, "2026-02-01 12:00:00")
    cont = await db_cont.get_container(cont_id)
    assert cont["status"] == "departed"
    assert cont["departure_date"] == "2026-02-01 12:00:00"
    # Отмена вывоза
    await db_cont.undo_departure(cont_id)
    cont = await db_cont.get_container(cont_id)
    assert cont["status"] == "on_terminal"
    assert cont["departure_date"] is None


async def test_update_number_duplicate(test_db):
    """Дубликат номера возвращает False."""
    cid = await db_comp.add_company("Co")
    await db_cont.add_container("AAAA1111111", "AAAA 1111111", cid, "on_terminal", "2026-01-01")
    c2 = await db_cont.add_container("BBBB2222222", "BBBB 2222222", cid, "on_terminal", "2026-01-01")
    result = await db_cont.update_number(c2, "AAAA1111111", "AAAA 1111111")
    assert result is False


async def test_update_number_success(test_db):
    """Успешное обновление номера."""
    cid = await db_comp.add_company("Co")
    cont_id = await db_cont.add_container("XXXX0000001", "XXXX 0000001", cid, "on_terminal", "2026-01-01")
    result = await db_cont.update_number(cont_id, "YYYY0000001", "YYYY 0000001")
    assert result is True
    cont = await db_cont.get_container(cont_id)
    assert cont["number"] == "YYYY0000001"


async def test_delete_container(test_db):
    cid = await db_comp.add_company("Co")
    cont_id = await db_cont.add_container("CCCC3333333", "CCCC 3333333", cid, "on_terminal", "2026-01-01")
    await db_cont.delete_container(cont_id)
    assert await db_cont.get_container(cont_id) is None


async def test_count_by_status(test_db):
    cid = await db_comp.add_company("Co")
    await db_cont.add_container("AAAA0000001", "AAAA 0000001", cid, "on_terminal", "2026-01-01")
    await db_cont.add_container("AAAA0000002", "AAAA 0000002", cid, "on_terminal", "2026-01-01")
    await db_cont.add_container("AAAA0000003", "AAAA 0000003", cid, "in_transit", None)
    counts = await db_cont.count_by_status()
    assert counts["on_terminal"] == 2
    assert counts["in_transit"] == 1
    assert counts["departed"] == 0


async def test_list_active_pagination(test_db):
    """Пагинация активных контейнеров."""
    cid = await db_comp.add_company("Co")
    for i in range(5):
        await db_cont.add_container(f"PAGG{i:07d}", f"PAGG {i:07d}", cid, "on_terminal", f"2026-01-{i+1:02d}")
    rows, total = await db_cont.list_active(page=1, per_page=3)
    assert total == 5
    assert len(rows) == 3
    rows2, _ = await db_cont.list_active(page=2, per_page=3)
    assert len(rows2) == 2


# --- Users ---


async def test_upsert_new_admin(test_db):
    """Админ из env получает роль full."""
    role = await db_users.upsert_user(111111, "admin", "Admin User", frozenset({111111}))
    assert role == "full"


async def test_upsert_new_regular_user(test_db):
    """Обычный пользователь получает роль none."""
    role = await db_users.upsert_user(999999, "user", "Regular", frozenset({111111}))
    assert role == "none"


async def test_set_and_get_role(test_db):
    await db_users.upsert_user(555555, "op", "Operator", frozenset({111111}))
    await db_users.set_role(555555, "reports_only")
    role = await db_users.get_role(555555)
    assert role == "reports_only"


async def test_list_users(test_db):
    """Список пользователей содержит админа из init_db."""
    users = await db_users.list_users()
    tg_ids = [u["tg_id"] for u in users]
    assert 111111 in tg_ids


# --- Settings ---


async def test_default_settings_seeded(test_db):
    """init_db засеял глобальные настройки."""
    settings = await db_settings.get_all_settings()
    assert settings["default_entry_fee"] == 20.0
    assert settings["default_free_days"] == 30
    assert settings["default_storage_rate"] == 20.0
    assert settings["default_storage_period_days"] == 30


async def test_update_setting(test_db):
    await db_settings.set_setting("default_entry_fee", 50.0)
    val = await db_settings.get_setting("default_entry_fee")
    assert val == 50.0


async def test_get_setting_nonexistent(test_db):
    """Несуществующий ключ возвращает None."""
    val = await db_settings.get_setting("nonexistent_key")
    assert val is None
