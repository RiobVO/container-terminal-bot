"""Smoke-тесты: приложение стартует без ошибок."""

import pytest


@pytest.mark.asyncio
async def test_init_db_creates_tables(test_db):
    """init_db создаёт все 4 таблицы."""
    import aiosqlite

    async with aiosqlite.connect(test_db) as conn:
        rows = await (
            await conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ).fetchall()
        table_names = sorted(r[0] for r in rows)
        assert "companies" in table_names
        assert "containers" in table_names
        assert "global_settings" in table_names
        assert "users" in table_names


def test_setup_routers_no_crash():
    """setup_routers не падает при регистрации роутеров."""
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    from handlers import setup_routers

    dp = Dispatcher(storage=MemoryStorage())
    setup_routers(dp)
    # Если дошли сюда — роутеры зарегистрированы без ошибок
