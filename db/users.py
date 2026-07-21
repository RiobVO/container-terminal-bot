"""CRUD для таблицы users."""
import logging

import aiosqlite

from db import get_db

logger = logging.getLogger(__name__)


async def get_user(tg_id: int) -> aiosqlite.Row | None:
    """Возвращает запись пользователя по tg_id."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
        ).fetchone()


async def upsert_user(
    tg_id: int,
    username: str | None,
    full_name: str | None,
    admin_ids: frozenset[int],
) -> str:
    """Создаёт или обновляет пользователя. Возвращает роль."""
    is_env_admin = tg_id in admin_ids
    async with get_db() as conn:
        row = await (
            await conn.execute("SELECT role FROM users WHERE tg_id=?", (tg_id,))
        ).fetchone()

        if row is None:
            role = "full" if is_env_admin else "none"
            await conn.execute(
                "INSERT INTO users (tg_id, username, full_name, role) VALUES (?, ?, ?, ?)",
                (tg_id, username, full_name, role),
            )
            await conn.commit()
            logger.info("Новый пользователь: tg_id=%s role=%s", tg_id, role)
            return role

        current_role = row[0]
        if is_env_admin and current_role != "full":
            await conn.execute(
                "UPDATE users SET role='full', username=?, full_name=? WHERE tg_id=?",
                (username, full_name, tg_id),
            )
            await conn.commit()
            return "full"

        await conn.execute(
            "UPDATE users SET username=?, full_name=? WHERE tg_id=?",
            (username, full_name, tg_id),
        )
        await conn.commit()
        return current_role


async def get_role(tg_id: int) -> str | None:
    """Возвращает роль пользователя или None."""
    async with get_db() as conn:
        row = await (
            await conn.execute("SELECT role FROM users WHERE tg_id=?", (tg_id,))
        ).fetchone()
        return row[0] if row else None


async def set_role(tg_id: int, role: str) -> None:
    """Устанавливает роль пользователя."""
    async with get_db() as conn:
        await conn.execute("UPDATE users SET role=? WHERE tg_id=?", (role, tg_id))
        await conn.commit()
    logger.info("Роль изменена: tg_id=%s -> %s", tg_id, role)


async def list_users() -> list[aiosqlite.Row]:
    """Возвращает всех пользователей."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute("SELECT * FROM users ORDER BY created_at")
        ).fetchall()
