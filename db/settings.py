"""CRUD для таблицы global_settings."""
import logging

from db import get_db

logger = logging.getLogger(__name__)


async def get_setting(key: str) -> float | None:
    """Возвращает значение настройки по ключу."""
    async with get_db() as conn:
        row = await (
            await conn.execute("SELECT value FROM global_settings WHERE key=?", (key,))
        ).fetchone()
        return row[0] if row else None


async def get_all_settings() -> dict[str, float]:
    """Возвращает все настройки как словарь."""
    async with get_db() as conn:
        rows = await (
            await conn.execute("SELECT key, value FROM global_settings")
        ).fetchall()
        return {r[0]: r[1] for r in rows}


async def set_setting(key: str, value: float) -> None:
    """Устанавливает значение настройки."""
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO global_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=?",
            (key, value, value),
        )
        await conn.commit()
    logger.info("Настройка обновлена: %s = %s", key, value)
