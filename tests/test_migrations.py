"""Тесты миграций схемы БД: v0→v1→v2, роль operator, бэкап, идемпотентность."""
import aiosqlite
import pytest

from db import init_db, migrations
from db.migrations import run_migrations


# --- Helpers ---


async def _create_db(path: str, script: str) -> None:
    """Создаёт БД с заданной сырыми DDL схемой."""
    async with aiosqlite.connect(path) as conn:
        await conn.executescript(script)
        await conn.commit()


async def _columns(path: str, table: str) -> list[str]:
    """Имена колонок таблицы."""
    async with aiosqlite.connect(path) as conn:
        rows = await (
            await conn.execute(f"PRAGMA table_info({table})")
        ).fetchall()
        return [r[1] for r in rows]


async def _fetchall(path: str, sql: str) -> list:
    async with aiosqlite.connect(path) as conn:
        return await (await conn.execute(sql)).fetchall()


def _backups(tmp_path) -> list:
    return list(tmp_path.glob("*.backup_*"))


# Схема v1: companies с monthly_rate, users без роли operator.
V1_DDL = """
CREATE TABLE global_settings (key TEXT PRIMARY KEY, value REAL);
CREATE TABLE companies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL COLLATE NOCASE,
    entry_fee    REAL,
    monthly_rate REAL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE users (
    tg_id      INTEGER PRIMARY KEY,
    username   TEXT,
    full_name  TEXT,
    role       TEXT NOT NULL DEFAULT 'none'
               CHECK (role IN ('full', 'reports_only', 'none')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Схема v0 (историческая, по докстрингу _migrate_v0_to_v1): companies
# с per-company storage_rate/storage_period_days, containers без status
# и display_number, users только tg_id+role.
V0_DDL = """
CREATE TABLE global_settings (key TEXT PRIMARY KEY, value REAL);
CREATE TABLE companies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    entry_fee           REAL,
    free_days           INTEGER,
    storage_rate        REAL,
    storage_period_days INTEGER
);
CREATE TABLE containers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    number         TEXT NOT NULL,
    company_id     INTEGER,
    type           TEXT,
    arrival_date   TEXT,
    departure_date TEXT,
    created_at     TEXT
);
CREATE TABLE users (
    tg_id INTEGER PRIMARY KEY,
    role  TEXT
);
"""


# --- run_migrations: краевые случаи ---


async def test_no_db_file_noop(tmp_path):
    """БД не существует — выход без ошибок и без бэкапа."""
    await run_migrations(str(tmp_path / "absent.db"))
    assert _backups(tmp_path) == []


async def test_fresh_v2_db_noop(tmp_path):
    """Свежая v2 из schema.py: все детекторы False, run_migrations — полный no-op."""
    db_path = str(tmp_path / "fresh.db")
    await init_db(
        path=db_path,
        admin_ids=frozenset(),
        default_entry_fee=20.0,
        default_free_days=30,
        default_storage_rate=20.0,
        default_storage_period_days=30,
    )
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO companies (id, name, entry_fee, free_days, "
            "storage_rate, storage_period_days) VALUES (1, 'Co', 50, 10, 5, 7)"
        )
        await conn.execute(
            "INSERT INTO containers (number, display_number, company_id) "
            "VALUES ('TEMU1234567', 'TEMU 1234567', 1)"
        )
        await conn.commit()
        # v2 не должна распознаваться ни одним детектором
        assert await migrations._needs_v0_to_v1(conn) is False
        assert await migrations._needs_v1_to_v2(conn) is False
        assert await migrations._needs_operator_role(conn) is False
        # audit_log уже создана DDL свежей установки
        assert await migrations._needs_audit_log(conn) is False

    await run_migrations(db_path)

    assert _backups(tmp_path) == []
    assert await _fetchall(
        db_path,
        "SELECT name, entry_fee, free_days, storage_rate, "
        "storage_period_days FROM companies",
    ) == [("Co", 50, 10, 5, 7)]
    assert await _fetchall(
        db_path, "SELECT number, display_number, status FROM containers"
    ) == [("TEMU1234567", "TEMU 1234567", "on_terminal")]


async def test_db_without_known_tables_noop(tmp_path):
    """В БД нет companies/users — все детекторы дают False."""
    db_path = str(tmp_path / "other.db")
    await _create_db(db_path, "CREATE TABLE misc (id INTEGER PRIMARY KEY);")
    await run_migrations(db_path)
    assert _backups(tmp_path) == []
    # Таблица не тронута
    assert await _columns(db_path, "misc") == ["id"]


# --- v1 → v2 ---


async def test_v1_to_v2_full(tmp_path):
    """Полная миграция v1→v2 + добавление роли operator + бэкап."""
    db_path = str(tmp_path / "v1.db")
    await _create_db(db_path, V1_DDL)
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO global_settings (key, value) VALUES "
            "('free_days', 14), ('default_monthly_rate', 25)"
        )
        await conn.execute(
            "INSERT INTO companies (id, name, entry_fee, monthly_rate) VALUES "
            "(1, 'Custom', 50, 60), (2, 'Standard', NULL, NULL)"
        )
        await conn.execute("INSERT INTO users (tg_id, role) VALUES (7, 'full')")
        await conn.commit()

    await run_migrations(db_path)

    # Бэкап создан до изменений
    assert len(_backups(tmp_path)) == 1

    cols = await _columns(db_path, "companies")
    assert "monthly_rate" not in cols
    assert {"free_days", "storage_rate", "storage_period_days"} <= set(cols)

    rows = await _fetchall(
        db_path,
        "SELECT name, entry_fee, free_days, storage_rate, "
        "storage_period_days FROM companies ORDER BY id",
    )
    # monthly_rate=60 → storage_rate=60, период и фри-дни по 30
    assert rows[0] == ("Custom", 50, 30, 60, 30)
    # monthly_rate=NULL → все тарифные поля NULL (стандарт)
    assert rows[1] == ("Standard", None, None, None, None)

    settings = dict(
        await _fetchall(db_path, "SELECT key, value FROM global_settings")
    )
    assert settings["default_free_days"] == 14
    assert settings["default_storage_rate"] == 25
    assert settings["default_storage_period_days"] == 30
    assert "free_days" not in settings
    assert "default_monthly_rate" not in settings

    # Роль operator добавлена в CHECK, данные пользователей сохранены
    (users_sql,) = (await _fetchall(
        db_path,
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'",
    ))[0]
    assert "operator" in users_sql
    assert await _fetchall(db_path, "SELECT tg_id, role FROM users") == [
        (7, "full")
    ]


async def test_v1_to_v2_default_settings(tmp_path):
    """Без старых ключей в global_settings подставляются дефолты 30/20."""
    db_path = str(tmp_path / "v1d.db")
    # users сразу с operator — operator-миграция не нужна
    await _create_db(db_path, V1_DDL.replace(
        "'full', 'reports_only', 'none'",
        "'full', 'operator', 'reports_only', 'none'",
    ))
    await run_migrations(db_path)

    settings = dict(
        await _fetchall(db_path, "SELECT key, value FROM global_settings")
    )
    assert settings["default_free_days"] == 30
    assert settings["default_storage_rate"] == 20
    assert settings["default_storage_period_days"] == 30


async def test_migrations_idempotent(tmp_path):
    """Повторный прогон после миграции ничего не меняет и не бэкапит."""
    db_path = str(tmp_path / "v1i.db")
    await _create_db(db_path, V1_DDL)
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO companies (name, monthly_rate) VALUES ('Co', 40)"
        )
        await conn.commit()

    await run_migrations(db_path)
    assert len(_backups(tmp_path)) == 1

    await run_migrations(db_path)  # второй прогон — noop
    assert len(_backups(tmp_path)) == 1
    rows = await _fetchall(
        db_path, "SELECT name, storage_rate FROM companies"
    )
    assert rows == [("Co", 40)]


# --- только operator-миграция (схема компаний уже v2) ---


async def test_operator_role_only(tmp_path):
    """Компании уже v2, мигрируется только CHECK роли в users."""
    db_path = str(tmp_path / "op.db")
    await init_db(
        path=db_path,
        admin_ids=frozenset(),
        default_entry_fee=20.0,
        default_free_days=30,
        default_storage_rate=20.0,
        default_storage_period_days=30,
    )
    # Откатываем users к схеме без operator
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript("""
            DROP TABLE users;
            CREATE TABLE users (
                tg_id      INTEGER PRIMARY KEY,
                username   TEXT,
                full_name  TEXT,
                role       TEXT NOT NULL DEFAULT 'none'
                           CHECK (role IN ('full', 'reports_only', 'none')),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO users (tg_id, role) VALUES (1, 'full');
        """)
        await conn.commit()

    await run_migrations(db_path)

    (users_sql,) = (await _fetchall(
        db_path,
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'",
    ))[0]
    assert "operator" in users_sql
    assert await _fetchall(db_path, "SELECT tg_id, role FROM users") == [
        (1, "full")
    ]
    assert len(_backups(tmp_path)) == 1


# --- v0 → v1 → v2 ---


async def test_v0_detector():
    """Детектор v0: тарифные колонки без monthly_rate, containers без status."""
    async with aiosqlite.connect(":memory:") as conn:
        await conn.execute(
            "CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT, "
            "entry_fee REAL, free_days INTEGER, storage_rate REAL, "
            "storage_period_days INTEGER)"
        )
        # companies есть, containers нет — не v0
        assert await migrations._needs_v0_to_v1(conn) is False
        await conn.execute(
            "CREATE TABLE containers (id INTEGER PRIMARY KEY, number TEXT, "
            "company_id INTEGER, type TEXT, arrival_date TEXT, "
            "departure_date TEXT, created_at TEXT)"
        )
        # Честная v0: все тарифные колонки + containers без status
        assert await migrations._needs_v0_to_v1(conn) is True


async def test_v0_detector_rejects_partial_tariff():
    """Нет одной из тарифных колонок — миграции нечего читать, не v0."""
    async with aiosqlite.connect(":memory:") as conn:
        await conn.execute(
            "CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT, "
            "entry_fee REAL, free_days INTEGER, storage_period_days INTEGER)"
        )
        await conn.execute(
            "CREATE TABLE containers (id INTEGER PRIMARY KEY, number TEXT)"
        )
        assert await migrations._needs_v0_to_v1(conn) is False


async def test_v1_not_recognized_as_v0():
    """Честная v1 (monthly_rate, containers со status) — детектор v0 False."""
    async with aiosqlite.connect(":memory:") as conn:
        await conn.execute(
            "CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT, "
            "entry_fee REAL, monthly_rate REAL, created_at TEXT)"
        )
        await conn.execute(
            "CREATE TABLE containers (id INTEGER PRIMARY KEY, number TEXT, "
            "display_number TEXT, company_id INTEGER, type TEXT, "
            "status TEXT NOT NULL DEFAULT 'on_terminal', registered_at TEXT, "
            "arrival_date TEXT, departure_date TEXT)"
        )
        assert await migrations._needs_v0_to_v1(conn) is False
        # v1 при этом корректно распознаётся детектором v1→v2
        assert await migrations._needs_v1_to_v2(conn) is True


async def test_v0_full_chain(tmp_path):
    """Цепочка v0→v1→v2→operator на честной v0-схеме без подмены детектора."""
    db_path = str(tmp_path / "v0.db")
    await _create_db(db_path, V0_DDL)
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO global_settings (key, value) VALUES "
            "('free_days', 30), ('default_monthly_rate', 20)"
        )
        # Покрываем все ветки пересчёта тарифа:
        # A: entry_fee=20 → NULL, rate=20/30дн → monthly 20 → NULL
        # B: кастомные entry_fee и ставка при периоде 30
        # C: entry_fee=0 → NULL, период 5 дн → пересчёт на 30 дн
        # D: тарифа нет вообще
        # E: период NULL → принимается за 1 день
        # F: пересчёт даёт ровно 20 → NULL (стандарт)
        await conn.execute(
            "INSERT INTO companies "
            "(id, name, entry_fee, free_days, storage_rate, "
            "storage_period_days) VALUES "
            "(1, 'A', 20, 30, 20, 30), "
            "(2, 'B', 50, 30, 60, 30), "
            "(3, 'C', 0, 30, 10, 5), "
            "(4, 'D', NULL, 30, NULL, 30), "
            "(5, 'E', 30, 30, 5, NULL), "
            "(6, 'F', 10, 30, 10, 15)"
        )
        await conn.execute(
            "INSERT INTO containers "
            "(id, number, company_id, type, arrival_date, departure_date, "
            "created_at) VALUES "
            "(1, 'temu 1234567', 1, '40ft', '2026-01-01', NULL, "
            "'2026-01-01 10:00:00'), "
            "(2, 'MSCU-7654321', 2, NULL, '2026-01-02', '2026-02-01', "
            "'2026-01-02 09:00:00'), "
            "(3, 'AB1', NULL, NULL, NULL, NULL, '2026-01-03 08:00:00')"
        )
        await conn.execute(
            "INSERT INTO users (tg_id, role) VALUES "
            "(1, 'admin'), (2, 'operator'), (3, 'viewer')"
        )
        await conn.commit()

    await run_migrations(db_path)

    assert len(_backups(tmp_path)) == 1

    # companies дошли до v2 (v0→v1 даёт monthly_rate, v1→v2 его убирает)
    cols = await _columns(db_path, "companies")
    assert "monthly_rate" not in cols
    assert "storage_rate" in cols
    rows = await _fetchall(
        db_path,
        "SELECT id, name, entry_fee, free_days, storage_rate, "
        "storage_period_days FROM companies ORDER BY id",
    )
    assert rows[0] == (1, "A", None, None, None, None)
    assert rows[1] == (2, "B", 50, 30, 60, 30)
    assert rows[2] == (3, "C", None, 30, 60.0, 30)
    assert rows[3] == (4, "D", None, None, None, None)
    assert rows[4] == (5, "E", 30, 30, 150.0, 30)
    assert rows[5] == (6, "F", 10, None, None, None)

    # containers: нормализация номера, display_number, статусы
    conts = await _fetchall(
        db_path,
        "SELECT id, number, display_number, status FROM containers "
        "ORDER BY id",
    )
    assert conts[0] == (1, "TEMU1234567", "TEMU 1234567", "on_terminal")
    assert conts[1] == (2, "MSCU7654321", "MSCU 7654321", "departed")
    # Номер короче 4 символов — display_number остаётся исходным
    assert conts[2] == (3, "AB1", "AB1", "on_terminal")

    # users: маппинг ролей + итоговый CHECK с operator
    users = await _fetchall(
        db_path, "SELECT tg_id, role FROM users ORDER BY tg_id"
    )
    assert users == [(1, "full"), (2, "full"), (3, "none")]
    (users_sql,) = (await _fetchall(
        db_path,
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'",
    ))[0]
    assert "operator" in users_sql

    # Повторный прогон после полной цепочки — noop без нового бэкапа
    await run_migrations(db_path)
    assert len(_backups(tmp_path)) == 1


# --- audit_log: аддитивная миграция на v2-БД ---


async def _make_v2_without_audit(tmp_path) -> str:
    """v2-БД «как в проде до аудита»: свежая схема минус audit_log."""
    db_path = str(tmp_path / "prod_v2.db")
    await init_db(
        path=db_path,
        admin_ids=frozenset({1}),
        default_entry_fee=20.0,
        default_free_days=30,
        default_storage_rate=20.0,
        default_storage_period_days=30,
    )
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript("""
            DROP INDEX idx_audit_entity;
            DROP TABLE audit_log;
            INSERT INTO companies (id, name, entry_fee, free_days,
                storage_rate, storage_period_days)
                VALUES (1, 'Custom', 50, 10, 5, 7), (2, 'Std', NULL, NULL, NULL, NULL);
            INSERT INTO containers (number, display_number, company_id,
                type, status, arrival_date)
                VALUES ('TEMU1234567', 'TEMU 1234567', 1, '40HQ',
                        'on_terminal', '2026-06-01 10:00:00'),
                       ('MSCU7654321', 'MSCU 7654321', 2, NULL,
                        'departed', '2026-05-01 09:00:00');
            INSERT INTO users (tg_id, role) VALUES (7, 'operator');
        """)
        await conn.commit()
    return db_path


async def _schema_objects(db_path: str) -> set[tuple[str, str]]:
    rows = await _fetchall(
        db_path,
        "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'",
    )
    return set(rows)


async def test_audit_log_migration_additive_only(tmp_path):
    """Прод-кейс: на v2-БД с данными добавляются ТОЛЬКО таблица и индекс.

    Существующие таблицы и строки остаются байт-в-байт теми же.
    """
    db_path = await _make_v2_without_audit(tmp_path)

    before_objects = await _schema_objects(db_path)
    before_companies = await _fetchall(db_path, "SELECT * FROM companies")
    before_containers = await _fetchall(db_path, "SELECT * FROM containers")
    before_users = await _fetchall(db_path, "SELECT * FROM users")
    before_settings = await _fetchall(db_path, "SELECT * FROM global_settings")

    await run_migrations(db_path)

    # Бэкап существующим механизмом — до изменений
    assert len(_backups(tmp_path)) == 1
    # Добавились ровно два объекта схемы
    added = await _schema_objects(db_path) - before_objects
    assert added == {("table", "audit_log"), ("index", "idx_audit_entity")}
    # Данные не тронуты
    assert await _fetchall(db_path, "SELECT * FROM companies") == before_companies
    assert await _fetchall(db_path, "SELECT * FROM containers") == before_containers
    assert await _fetchall(db_path, "SELECT * FROM users") == before_users
    assert await _fetchall(db_path, "SELECT * FROM global_settings") == before_settings
    # Новая таблица пуста и принимает записи
    assert await _fetchall(db_path, "SELECT COUNT(*) FROM audit_log") == [(0,)]


async def test_audit_log_migration_idempotent(tmp_path):
    """Повторный прогон после создания audit_log — noop без нового бэкапа."""
    db_path = await _make_v2_without_audit(tmp_path)

    await run_migrations(db_path)
    assert len(_backups(tmp_path)) == 1

    # Записи аудита переживают повторный прогон
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO audit_log (action, entity_type, entity_id, "
            "entity_label) VALUES ('вывезен', 'container', 1, 'TEMU 1234567')"
        )
        await conn.commit()

    await run_migrations(db_path)
    assert len(_backups(tmp_path)) == 1
    assert await _fetchall(
        db_path, "SELECT action, entity_label FROM audit_log"
    ) == [("вывезен", "TEMU 1234567")]


async def test_needs_operator_role_no_sql_row(monkeypatch):
    """Защитная ветка: _has_table даёт True, а строки в sqlite_master нет."""
    async def _fake_has_table(conn, table):
        return True

    monkeypatch.setattr(migrations, "_has_table", _fake_has_table)
    async with aiosqlite.connect(":memory:") as conn:
        assert await migrations._needs_operator_role(conn) is False
