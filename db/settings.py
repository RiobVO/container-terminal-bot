"""CRUD для таблицы global_settings."""
import logging
import time

from db import get_db

logger = logging.getLogger(__name__)

# Кэш для get_all_settings: меняется через /settings раз в полгода,
# а дёргается из карточки контейнера и каждого расчёта стоимости —
# десятки раз в час. Без кэша это десятки лишних SELECT на пустом месте.
_SETTINGS_CACHE: dict[str, float] | None = None
_SETTINGS_CACHE_EXPIRES_AT: float = 0.0
_SETTINGS_TTL_SECONDS = 60.0


def _invalidate_settings_cache() -> None:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_EXPIRES_AT
    _SETTINGS_CACHE = None
    _SETTINGS_CACHE_EXPIRES_AT = 0.0


async def get_setting(key: str) -> float | None:
    """Возвращает значение настройки по ключу."""
    async with get_db() as conn:
        row = await (
            await conn.execute("SELECT value FROM global_settings WHERE key=?", (key,))
        ).fetchone()
        return row[0] if row else None


async def get_all_settings() -> dict[str, float]:
    """Возвращает все настройки как словарь (с кэшем по TTL)."""
    global _SETTINGS_CACHE, _SETTINGS_CACHE_EXPIRES_AT
    now = time.monotonic()
    if _SETTINGS_CACHE is not None and _SETTINGS_CACHE_EXPIRES_AT > now:
        return _SETTINGS_CACHE
    async with get_db() as conn:
        rows = await (
            await conn.execute("SELECT key, value FROM global_settings")
        ).fetchall()
        result = {r[0]: r[1] for r in rows}
    _SETTINGS_CACHE = result
    _SETTINGS_CACHE_EXPIRES_AT = now + _SETTINGS_TTL_SECONDS
    return result


async def set_setting(key: str, value: float) -> None:
    """Устанавливает значение настройки."""
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO global_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=?",
            (key, value, value),
        )
        await conn.commit()
    # Кэш стал неактуальным — следующий get_all_settings перезапросит.
    _invalidate_settings_cache()
    logger.info("Настройка обновлена: %s = %s", key, value)
