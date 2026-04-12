"""CRUD для таблицы companies."""
import logging

import aiosqlite

from db import get_db

logger = logging.getLogger(__name__)


async def list_companies() -> list[aiosqlite.Row]:
    """Возвращает все компании."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute("SELECT * FROM companies ORDER BY name")
        ).fetchall()


async def list_companies_with_active_counts() -> list[aiosqlite.Row]:
    """Список компаний + счётчик активных контейнеров одним JOIN'ом.

    Активные = статусы on_terminal и in_transit. Сортировка по имени
    регистронезависимо (COLLATE NOCASE), чтобы избежать N+1 и чтобы
    порядок совпадал с тем, который ожидает клавиатура списка компаний.
    """
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT c.id, c.name, "
                "COUNT(CASE WHEN ct.status IN ('on_terminal','in_transit') "
                "THEN 1 END) AS active_count "
                "FROM companies c "
                "LEFT JOIN containers ct ON ct.company_id = c.id "
                "GROUP BY c.id, c.name "
                "ORDER BY c.name COLLATE NOCASE"
            )
        ).fetchall()


async def get_company(company_id: int) -> aiosqlite.Row | None:
    """Возвращает компанию по id."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT * FROM companies WHERE id=?", (company_id,)
            )
        ).fetchone()


async def get_company_by_name_ci(name: str) -> aiosqlite.Row | None:
    """Регистронезависимый поиск по имени."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT * FROM companies WHERE LOWER(name)=LOWER(?)", (name,)
            )
        ).fetchone()


async def add_company(
    name: str,
    entry_fee: float | None = None,
    free_days: int | None = None,
    storage_rate: float | None = None,
    storage_period_days: int | None = None,
) -> int:
    """Добавляет компанию, возвращает id."""
    async with get_db() as conn:
        cursor = await conn.execute(
            "INSERT INTO companies "
            "(name, entry_fee, free_days, storage_rate, storage_period_days) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, entry_fee, free_days, storage_rate, storage_period_days),
        )
        await conn.commit()
        logger.info("Компания добавлена: %s (id=%s)", name, cursor.lastrowid)
        return cursor.lastrowid


async def update_entry_fee(company_id: int, value: float | None) -> None:
    """Стоимость входа (NULL = стандартный)."""
    async with get_db() as conn:
        await conn.execute(
            "UPDATE companies SET entry_fee=? WHERE id=?",
            (value, company_id),
        )
        await conn.commit()


async def update_free_days(company_id: int, value: int | None) -> None:
    """Бесплатные дни (NULL = стандартный)."""
    async with get_db() as conn:
        await conn.execute(
            "UPDATE companies SET free_days=? WHERE id=?",
            (value, company_id),
        )
        await conn.commit()


async def update_storage_rate(company_id: int, value: float | None) -> None:
    """Ставка платного хранения за один период (NULL = стандартная)."""
    async with get_db() as conn:
        await conn.execute(
            "UPDATE companies SET storage_rate=? WHERE id=?",
            (value, company_id),
        )
        await conn.commit()


async def update_storage_period_days(
    company_id: int, value: int | None
) -> None:
    """Период начисления ставки в днях (1=ежедневный, 30=ежемесячный)."""
    async with get_db() as conn:
        await conn.execute(
            "UPDATE companies SET storage_period_days=? WHERE id=?",
            (value, company_id),
        )
        await conn.commit()


async def rename_company(company_id: int, new_name: str) -> None:
    """Переименовывает компанию."""
    async with get_db() as conn:
        await conn.execute(
            "UPDATE companies SET name=? WHERE id=?",
            (new_name, company_id),
        )
        await conn.commit()
    logger.info("Компания переименована: id=%s -> %s", company_id, new_name)


async def delete_company(company_id: int) -> None:
    """Удаляет компанию. Контейнеры получат company_id=NULL."""
    async with get_db() as conn:
        await conn.execute(
            "DELETE FROM companies WHERE id=?", (company_id,)
        )
        await conn.commit()
    logger.info("Компания удалена: id=%s", company_id)


async def count_total_containers(company_id: int) -> int:
    """Общее количество контейнеров компании за всё время."""
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "SELECT COUNT(*) FROM containers WHERE company_id=?",
                (company_id,),
            )
        ).fetchone()
        return row[0]
