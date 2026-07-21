import logging

import aiosqlite

from db.migrations import run_migrations
from db.schema import DDL

logger = logging.getLogger(__name__)

_DB_PATH: str = "bot.db"
_ADMIN_IDS: frozenset[int] = frozenset()


def get_db() -> aiosqlite.Connection:
    """Возвращает новое соединение к БД."""
    return aiosqlite.connect(_DB_PATH)


async def init_db(
    path: str,
    admin_ids: frozenset[int],
    default_entry_fee: float,
    default_free_days: int,
    default_storage_rate: float,
    default_storage_period_days: int,
) -> None:
    """Инициализирует БД: миграции, DDL, глобальные настройки, админы."""
    global _DB_PATH, _ADMIN_IDS
    _DB_PATH = path
    _ADMIN_IDS = admin_ids

    await run_migrations(path)

    async with aiosqlite.connect(path) as conn:
        await conn.executescript(DDL)

        # Глобальные настройки по умолчанию (не перезаписывают существующие)
        for key, value in [
            ("default_entry_fee", default_entry_fee),
            ("default_free_days", default_free_days),
            ("default_storage_rate", default_storage_rate),
            ("default_storage_period_days", default_storage_period_days),
        ]:
            await conn.execute(
                "INSERT OR IGNORE INTO global_settings (key, value) VALUES (?, ?)",
                (key, value),
            )

        # Админы из .env получают роль full
        for tg_id in admin_ids:
            await conn.execute(
                "INSERT INTO users (tg_id, role) VALUES (?, 'full') "
                "ON CONFLICT(tg_id) DO UPDATE SET role='full'",
                (tg_id,),
            )

        await conn.commit()

    logger.info("БД инициализирована: %s, admin_ids=%s", path, admin_ids)
