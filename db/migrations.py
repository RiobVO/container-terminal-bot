"""Миграции схемы БД.

Текущая схема (v2) — гибкая модель тарифов: у компании есть entry_fee,
free_days, storage_rate, storage_period_days (каждое NULL = стандартное
из global_settings).

Предыдущие ревизии, которые умеет мигрировать этот модуль:
- v0 (самая старая): companies имел free_days / storage_rate /
  storage_period_days ещё на старом движке, без нормализованных номеров
  и без поля status у containers.
- v1: companies имел entry_fee + monthly_rate, global_settings содержал
  default_monthly_rate и free_days (глобальная константа).
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _has_table(conn: aiosqlite.Connection, table: str) -> bool:
    row = await (
        await conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
    ).fetchone()
    return row is not None


async def _has_column(
    conn: aiosqlite.Connection, table: str, column: str
) -> bool:
    rows = await (
        await conn.execute(f"PRAGMA table_info({table})")
    ).fetchall()
    return any(r[1] == column for r in rows)


def _make_backup(db_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{ts}"
    shutil.copy2(db_path, backup_path)
    logger.info("Бэкап БД: %s", backup_path)
    return backup_path


# ---------------------------------------------------------------------------
# Детекторы
# ---------------------------------------------------------------------------


async def _needs_v0_to_v1(conn: aiosqlite.Connection) -> bool:
    """v0: старый тариф в companies и containers ещё без колонки status.

    По набору колонок companies честная v0 неотличима от v2 — обе содержат
    free_days / storage_rate / storage_period_days (именно их читает
    _migrate_v0_to_v1 из companies_old). Поэтому решающий признак —
    containers.status: колонка появилась в миграции v0→v1 и присутствует
    во всех последующих ревизиях (schema.py создаёт её всегда), а в v0
    её не было. v1 отсекается по monthly_rate и отсутствию тарифных колонок.
    """
    if not await _has_table(conn, "companies"):
        return False
    if not await _has_table(conn, "containers"):
        return False
    # v1: companies(entry_fee, monthly_rate) — это не v0.
    if await _has_column(conn, "companies", "monthly_rate"):
        return False
    # Миграция читает эти колонки из companies_old — без них она невозможна.
    for col in ("free_days", "storage_rate", "storage_period_days"):
        if not await _has_column(conn, "companies", col):
            return False
    # Единственное, что отличает v0 от v2: в v0 containers без status.
    return not await _has_column(conn, "containers", "status")


async def _needs_v1_to_v2(conn: aiosqlite.Connection) -> bool:
    """v1: companies имел monthly_rate без storage_rate."""
    if not await _has_table(conn, "companies"):
        return False
    return (
        await _has_column(conn, "companies", "monthly_rate")
        and not await _has_column(conn, "companies", "storage_rate")
    )


# ---------------------------------------------------------------------------
# v0 → v1: старые устаревшие схемы (сохранён для обратной совместимости)
# ---------------------------------------------------------------------------


async def _migrate_v0_to_v1(conn: aiosqlite.Connection) -> None:
    """Конвертация самой старой схемы в v1 (entry_fee + monthly_rate)."""
    logger.info("Миграция v0 → v1: устаревшая схема companies")

    await conn.execute("ALTER TABLE companies RENAME TO companies_old")
    await conn.execute("""
        CREATE TABLE companies (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT UNIQUE NOT NULL COLLATE NOCASE,
            entry_fee    REAL,
            monthly_rate REAL,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    old_rows = await (
        await conn.execute(
            "SELECT id, name, entry_fee, free_days, storage_rate, "
            "storage_period_days FROM companies_old"
        )
    ).fetchall()

    for cid, name, entry_fee, _free_days, storage_rate, period in old_rows:
        new_entry_fee = entry_fee if entry_fee not in (None, 0, 20) else None

        new_monthly_rate: float | None = None
        if storage_rate and storage_rate != 0:
            p = period if period and period > 0 else 1
            if p == 30:
                new_monthly_rate = storage_rate
            else:
                new_monthly_rate = round(storage_rate * 30 / p, 2)
            if new_monthly_rate == 20:
                new_monthly_rate = None

        await conn.execute(
            "INSERT INTO companies (id, name, entry_fee, monthly_rate) "
            "VALUES (?, ?, ?, ?)",
            (cid, name, new_entry_fee, new_monthly_rate),
        )

    await conn.execute("DROP TABLE companies_old")
    logger.info("Мигрировано компаний v0 → v1: %d", len(old_rows))

    # Устаревший containers: status не было — добавляем
    if not await _has_column(conn, "containers", "status"):
        await conn.execute("ALTER TABLE containers RENAME TO containers_old")
        await conn.execute("""
            CREATE TABLE containers (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                number          TEXT UNIQUE NOT NULL,
                display_number  TEXT NOT NULL,
                company_id      INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                type            TEXT,
                status          TEXT NOT NULL DEFAULT 'on_terminal'
                                CHECK (status IN ('in_transit', 'on_terminal', 'departed')),
                registered_at   TEXT NOT NULL DEFAULT (datetime('now')),
                arrival_date    TEXT,
                departure_date  TEXT
            )
        """)
        old_containers = await (
            await conn.execute(
                "SELECT id, number, company_id, type, arrival_date, "
                "departure_date, created_at FROM containers_old"
            )
        ).fetchall()
        for cid, number, company_id, ctype, arrival, departure, created in old_containers:
            normalized = number.upper().replace(" ", "").replace("-", "")
            display = (
                f"{normalized[:4]} {normalized[4:]}"
                if len(normalized) >= 4
                else number
            )
            status = "departed" if departure else "on_terminal"
            await conn.execute(
                "INSERT INTO containers "
                "(id, number, display_number, company_id, type, status, "
                "registered_at, arrival_date, departure_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, normalized, display, company_id, ctype, status,
                 created, arrival, departure),
            )
        await conn.execute("DROP TABLE containers_old")
        logger.info("Мигрировано контейнеров v0 → v1: %d", len(old_containers))

    # Устаревший users
    if not await _has_column(conn, "users", "username"):
        await conn.execute("ALTER TABLE users RENAME TO users_old")
        await conn.execute("""
            CREATE TABLE users (
                tg_id      INTEGER PRIMARY KEY,
                username   TEXT,
                full_name  TEXT,
                role       TEXT NOT NULL DEFAULT 'none'
                           CHECK (role IN ('full', 'reports_only', 'none')),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        old_users = await (
            await conn.execute("SELECT tg_id, role FROM users_old")
        ).fetchall()
        for tg_id, role in old_users:
            new_role = "full" if role in ("admin", "operator") else "none"
            await conn.execute(
                "INSERT INTO users (tg_id, role) VALUES (?, ?)",
                (tg_id, new_role),
            )
        await conn.execute("DROP TABLE users_old")
        logger.info("Мигрировано пользователей v0 → v1: %d", len(old_users))


# ---------------------------------------------------------------------------
# v1 → v2: гибкая модель тарифа
# ---------------------------------------------------------------------------


async def _migrate_v1_to_v2(conn: aiosqlite.Connection) -> None:
    """Заменяет monthly_rate на free_days / storage_rate / storage_period_days.

    Для каждой компании: если monthly_rate IS NOT NULL —
    storage_rate := monthly_rate, storage_period_days := 30, free_days := 30.
    Иначе все три поля остаются NULL (стандартные значения).

    global_settings: добавляются default_free_days, default_storage_rate,
    default_storage_period_days; удаляются устаревшие free_days и
    default_monthly_rate.
    """
    logger.info(
        "Миграция v1 → v2: гибкая модель тарифа "
        "(monthly_rate → storage_rate/storage_period_days/free_days)"
    )

    # Пересобираем companies через промежуточную таблицу —
    # переносим данные и гарантированно избавляемся от monthly_rate.
    await conn.execute("ALTER TABLE companies RENAME TO companies_old_v1")
    await conn.execute("""
        CREATE TABLE companies (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            name                 TEXT UNIQUE NOT NULL COLLATE NOCASE,
            entry_fee            REAL,
            free_days            INTEGER,
            storage_rate         REAL,
            storage_period_days  INTEGER,
            created_at           TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    rows = await (
        await conn.execute(
            "SELECT id, name, entry_fee, monthly_rate, created_at "
            "FROM companies_old_v1"
        )
    ).fetchall()

    migrated = 0
    for cid, name, entry_fee, monthly_rate, created_at in rows:
        if monthly_rate is not None:
            free_days = 30
            storage_rate = monthly_rate
            storage_period = 30
        else:
            free_days = None
            storage_rate = None
            storage_period = None

        await conn.execute(
            "INSERT INTO companies "
            "(id, name, entry_fee, free_days, storage_rate, "
            "storage_period_days, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, name, entry_fee, free_days, storage_rate,
             storage_period, created_at),
        )
        migrated += 1

    await conn.execute("DROP TABLE companies_old_v1")
    logger.info("Мигрировано компаний v1 → v2: %d", migrated)

    # global_settings: переносим значения и удаляем устаревшие ключи.
    old_settings_rows = await (
        await conn.execute("SELECT key, value FROM global_settings")
    ).fetchall()
    old_settings = {k: v for k, v in old_settings_rows}

    new_default_free_days = old_settings.get("free_days", 30)
    new_default_storage_rate = old_settings.get("default_monthly_rate", 20)

    for key, value in [
        ("default_free_days", new_default_free_days),
        ("default_storage_rate", new_default_storage_rate),
        ("default_storage_period_days", 30),
    ]:
        await conn.execute(
            "INSERT INTO global_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    await conn.execute(
        "DELETE FROM global_settings WHERE key IN "
        "('free_days', 'default_monthly_rate')"
    )
    logger.info(
        "global_settings обновлены: default_free_days=%s, "
        "default_storage_rate=%s, default_storage_period_days=30",
        new_default_free_days, new_default_storage_rate,
    )


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------


async def _needs_operator_role(conn: aiosqlite.Connection) -> bool:
    """Проверяет, нужна ли миграция для добавления роли operator."""
    if not await _has_table(conn, "users"):
        return False
    # Проверяем CHECK constraint через sql схемы таблицы
    row = await (
        await conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
        )
    ).fetchone()
    if row is None:
        return False
    return "operator" not in row[0]


async def _add_operator_role(conn: aiosqlite.Connection) -> None:
    """Пересоздаёт таблицу users с поддержкой роли operator."""
    logger.info("Добавляю роль operator в таблицу users...")
    await conn.executescript("""
        CREATE TABLE users_new (
            tg_id      INTEGER PRIMARY KEY,
            username   TEXT,
            full_name  TEXT,
            role       TEXT NOT NULL DEFAULT 'none'
                       CHECK (role IN ('full', 'operator', 'reports_only', 'none')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO users_new SELECT * FROM users;
        DROP TABLE users;
        ALTER TABLE users_new RENAME TO users;
    """)
    logger.info("Роль operator добавлена")


async def _needs_audit_log(conn: aiosqlite.Connection) -> bool:
    """Проверяет, нужна ли таблица audit_log (появилась после v2).

    Создаём только в БД с нашей схемой (есть containers) — чужие или
    пустые файлы не трогаем, как и остальные детекторы.
    """
    if not await _has_table(conn, "containers"):
        return False
    return not await _has_table(conn, "audit_log")


async def _create_audit_log(conn: aiosqlite.Connection) -> None:
    """Создаёт append-only таблицу аудита и индекс.

    Строго аддитивно: существующие таблицы и данные не изменяются.
    DDL обязан совпадать со schema.py (для свежих установок).
    """
    logger.info("Создаю таблицу audit_log...")
    await conn.executescript("""
        CREATE TABLE audit_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            actor_tg_id   INTEGER,
            actor_name    TEXT,
            action        TEXT NOT NULL,
            entity_type   TEXT NOT NULL
                          CHECK (entity_type IN ('container', 'company', 'user', 'settings')),
            entity_id     INTEGER,
            entity_label  TEXT,
            details       TEXT
        );
        CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
    """)
    logger.info("Таблица audit_log создана")


async def run_migrations(db_path: str) -> None:
    """Выполняет все необходимые миграции последовательно."""
    if not Path(db_path).exists():
        logger.info("БД не существует, миграция не требуется")
        return

    async with aiosqlite.connect(db_path) as conn:
        need_v0 = await _needs_v0_to_v1(conn)
        need_v1 = not need_v0 and await _needs_v1_to_v2(conn)
        need_operator = await _needs_operator_role(conn)
        need_audit = await _needs_audit_log(conn)

        if not need_v0 and not need_v1 and not need_operator and not need_audit:
            logger.info("Миграция не требуется")
            return

        _make_backup(db_path)

        if need_v0:
            await _migrate_v0_to_v1(conn)
            await conn.commit()

        # После v0→v1 схема может стать v1 — проверяем повторно.
        if await _needs_v1_to_v2(conn):
            await _migrate_v1_to_v2(conn)
            await conn.commit()

        if need_operator:
            await _add_operator_role(conn)
            await conn.commit()

        if need_audit:
            await _create_audit_log(conn)
            await conn.commit()

        logger.info("Миграция завершена успешно")
