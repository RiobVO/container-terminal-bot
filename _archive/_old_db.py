import logging
from datetime import date

import aiosqlite

logger = logging.getLogger(__name__)

_DB_PATH: str = "container.db"
_ADMIN_IDS: frozenset = frozenset()

DDL = """
CREATE TABLE IF NOT EXISTS companies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE,
    entry_fee           REAL NOT NULL DEFAULT 0,
    free_days           INTEGER NOT NULL DEFAULT 0,
    storage_rate        REAL NOT NULL DEFAULT 0,
    storage_period_days INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS containers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    number         TEXT NOT NULL UNIQUE,
    company_id     INTEGER NOT NULL REFERENCES companies(id),
    type           TEXT NOT NULL CHECK (type IN ('20GP','20HQ','40GP','40HQ','45HQ')),
    arrival_date   TEXT NOT NULL,
    departure_date TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_containers_arrival ON containers(arrival_date);
CREATE INDEX IF NOT EXISTS idx_containers_company ON containers(company_id);

CREATE TABLE IF NOT EXISTS users (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER NOT NULL UNIQUE,
    role  TEXT NOT NULL CHECK (role IN ('admin','operator'))
);
"""


async def init_db(path: str, admin_ids: frozenset) -> None:
    """Создаёт таблицы и засевает админов из ADMIN_IDS."""
    global _DB_PATH, _ADMIN_IDS
    _DB_PATH = path
    _ADMIN_IDS = admin_ids

    async with aiosqlite.connect(_DB_PATH) as db:
        await db.executescript(DDL)
        # Засеиваем всех известных админов, не понижая существующих
        for tg_id in admin_ids:
            await db.execute(
                "INSERT INTO users (tg_id, role) VALUES (?, 'admin') "
                "ON CONFLICT(tg_id) DO UPDATE SET role='admin' WHERE role!='admin'",
                (tg_id,),
            )
        await db.commit()
    logger.info("БД инициализирована: %s, admin_ids=%s", path, admin_ids)


def _conn():
    return aiosqlite.connect(_DB_PATH)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


async def upsert_user(tg_id: int) -> str:
    """
    Создаёт или обновляет запись пользователя.
    Роль: admin если tg_id в ADMIN_IDS, иначе operator.
    Существующих админов не понижаем — только повышаем.
    Возвращает итоговую роль.
    """
    is_admin_env = tg_id in _ADMIN_IDS
    async with _conn() as db:
        row = await (await db.execute("SELECT role FROM users WHERE tg_id=?", (tg_id,))).fetchone()
        if row is None:
            role = "admin" if is_admin_env else "operator"
            await db.execute("INSERT INTO users (tg_id, role) VALUES (?,?)", (tg_id, role))
            await db.commit()
            return role
        current_role = row[0]
        if is_admin_env and current_role != "admin":
            await db.execute("UPDATE users SET role='admin' WHERE tg_id=?", (tg_id,))
            await db.commit()
            return "admin"
        return current_role


async def get_user_role(tg_id: int) -> str | None:
    """Возвращает роль пользователя или None если не зарегистрирован."""
    async with _conn() as db:
        row = await (await db.execute("SELECT role FROM users WHERE tg_id=?", (tg_id,))).fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


async def list_companies() -> list[aiosqlite.Row]:
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute("SELECT * FROM companies ORDER BY name")).fetchall()


async def get_company(company_id: int) -> aiosqlite.Row | None:
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute("SELECT * FROM companies WHERE id=?", (company_id,))).fetchone()


async def get_company_by_name(name: str) -> aiosqlite.Row | None:
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        return await (
            await db.execute("SELECT * FROM companies WHERE name=?", (name,))
        ).fetchone()


async def add_company(
    name: str,
    entry_fee: float = 0,
    free_days: int = 0,
    storage_rate: float = 0,
    storage_period_days: int = 1,
) -> int:
    """Добавляет компанию, возвращает её id. Выбрасывает IntegrityError при дубликате имени."""
    async with _conn() as db:
        cursor = await db.execute(
            "INSERT INTO companies (name, entry_fee, free_days, storage_rate, storage_period_days) "
            "VALUES (?,?,?,?,?)",
            (name, entry_fee, free_days, storage_rate, storage_period_days),
        )
        await db.commit()
        logger.info("Компания добавлена: %s (id=%s)", name, cursor.lastrowid)
        return cursor.lastrowid


async def get_company_by_name_ci(name: str) -> aiosqlite.Row | None:
    """Регистронезависимый поиск компании по имени."""
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        return await (
            await db.execute("SELECT * FROM companies WHERE LOWER(name)=LOWER(?)", (name,))
        ).fetchone()


async def update_company_tariff(
    company_id: int,
    entry_fee: float,
    free_days: int,
    storage_rate: float,
    storage_period_days: int,
) -> None:
    """Обновляет тарифные параметры компании."""
    async with _conn() as db:
        await db.execute(
            "UPDATE companies SET entry_fee=?, free_days=?, storage_rate=?, storage_period_days=? "
            "WHERE id=?",
            (entry_fee, free_days, storage_rate, storage_period_days, company_id),
        )
        await db.commit()
    logger.info("Тариф обновлён: company_id=%s", company_id)


async def delete_company(company_id: int) -> None:
    """Удаляет компанию. Связанные контейнеры остаются в базе."""
    async with _conn() as db:
        await db.execute("DELETE FROM companies WHERE id=?", (company_id,))
        await db.commit()
    logger.info("Компания удалена: id=%s", company_id)


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------


async def find_container(number: str) -> aiosqlite.Row | None:
    """Ищет контейнер по нормализованному номеру, джойнит компанию."""
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        return await (
            await db.execute(
                "SELECT c.*, co.name AS company_name, co.entry_fee, co.free_days, "
                "co.storage_rate, co.storage_period_days "
                "FROM containers c "
                "JOIN companies co ON co.id = c.company_id "
                "WHERE c.number=?",
                (number,),
            )
        ).fetchone()


async def add_container(
    number: str,
    company_id: int,
    container_type: str,
    arrival_date: date,
) -> int | None:
    """
    Добавляет контейнер. Возвращает id или None при конфликте (дубликат номера).
    """
    try:
        async with _conn() as db:
            cursor = await db.execute(
                "INSERT INTO containers (number, company_id, type, arrival_date) VALUES (?,?,?,?)",
                (number, company_id, container_type, arrival_date.isoformat()),
            )
            await db.commit()
            logger.info("Контейнер зарегистрирован: %s company_id=%s", number, company_id)
            return cursor.lastrowid
    except aiosqlite.IntegrityError:
        logger.warning("Попытка добавить дубликат контейнера: %s", number)
        return None


async def set_departure(number: str, departure_date: date) -> bool:
    """
    Проставляет дату вывоза. Возвращает True при успехе, False если контейнер не найден
    или уже имеет дату вывоза.
    """
    async with _conn() as db:
        row = await (
            await db.execute(
                "SELECT departure_date FROM containers WHERE number=?", (number,)
            )
        ).fetchone()
        if row is None or row[0] is not None:
            return False
        await db.execute(
            "UPDATE containers SET departure_date=? WHERE number=?",
            (departure_date.isoformat(), number),
        )
        await db.commit()
        logger.info("Вывоз зафиксирован: %s -> %s", number, departure_date)
        return True


async def containers_by_month(
    company_id: int,
    year_month: str,
    departed_only: bool = False,
) -> list[aiosqlite.Row]:
    """
    Возвращает контейнеры компании за указанный месяц (YYYY-MM) по дате прибытия.
    При departed_only=True — только вывезенные.
    """
    sql = (
        "SELECT * FROM containers "
        "WHERE company_id=? AND substr(arrival_date,1,7)=?"
    )
    if departed_only:
        sql += " AND departure_date IS NOT NULL"
    sql += " ORDER BY arrival_date"
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute(sql, (company_id, year_month))).fetchall()
