"""CRUD для таблицы containers."""
import logging
from datetime import datetime

import aiosqlite

from db import get_db

logger = logging.getLogger(__name__)


async def get_container(container_id: int) -> aiosqlite.Row | None:
    """Возвращает контейнер с джойном компании."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT c.*, co.name AS company_name, "
                "co.entry_fee AS comp_entry_fee, "
                "co.free_days AS comp_free_days, "
                "co.storage_rate AS comp_storage_rate, "
                "co.storage_period_days AS comp_storage_period_days "
                "FROM containers c "
                "LEFT JOIN companies co ON co.id = c.company_id "
                "WHERE c.id=?",
                (container_id,),
            )
        ).fetchone()


async def find_by_number(normalized: str) -> aiosqlite.Row | None:
    """Ищет контейнер по нормализованному номеру."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT c.*, co.name AS company_name, "
                "co.entry_fee AS comp_entry_fee, "
                "co.free_days AS comp_free_days, "
                "co.storage_rate AS comp_storage_rate, "
                "co.storage_period_days AS comp_storage_period_days "
                "FROM containers c "
                "LEFT JOIN companies co ON co.id = c.company_id "
                "WHERE c.number=?",
                (normalized,),
            )
        ).fetchone()


async def list_active(page: int = 1, per_page: int = 8) -> tuple[list[aiosqlite.Row], int]:
    """Возвращает контейнеры on_terminal + in_transit с пагинацией и общее количество."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (
            await conn.execute(
                "SELECT COUNT(*) FROM containers WHERE status IN ('on_terminal', 'in_transit')"
            )
        ).fetchone()
        total = row[0]

        offset = (page - 1) * per_page
        rows = await (
            await conn.execute(
                "SELECT * FROM containers "
                "WHERE status IN ('on_terminal', 'in_transit') "
                "ORDER BY CASE status WHEN 'in_transit' THEN 0 ELSE 1 END, arrival_date DESC "
                "LIMIT ? OFFSET ?",
                (per_page, offset),
            )
        ).fetchall()
        return rows, total


async def list_departed(page: int = 1, per_page: int = 8) -> tuple[list[aiosqlite.Row], int]:
    """Возвращает вывезенные контейнеры с пагинацией."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (
            await conn.execute(
                "SELECT COUNT(*) FROM containers WHERE status='departed'"
            )
        ).fetchone()
        total = row[0]

        offset = (page - 1) * per_page
        rows = await (
            await conn.execute(
                "SELECT * FROM containers WHERE status='departed' "
                "ORDER BY departure_date DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            )
        ).fetchall()
        return rows, total


async def count_by_status() -> dict[str, int]:
    """Возвращает количество контейнеров по статусам."""
    async with get_db() as conn:
        rows = await (
            await conn.execute(
                "SELECT status, COUNT(*) FROM containers GROUP BY status"
            )
        ).fetchall()
        result = {"in_transit": 0, "on_terminal": 0, "departed": 0}
        for status, count in rows:
            result[status] = count
        return result


async def add_container(
    number: str,
    display_number: str,
    company_id: int,
    status: str,
    arrival_date: str | None,
    container_type: str | None = None,
) -> int:
    """Добавляет контейнер. Возвращает id."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as conn:
        cursor = await conn.execute(
            "INSERT INTO containers "
            "(number, display_number, company_id, status, type, "
            "registered_at, arrival_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                number,
                display_number,
                company_id,
                status,
                container_type,
                now,
                arrival_date,
            ),
        )
        await conn.commit()
        logger.info(
            "Контейнер добавлен: %s status=%s company_id=%s type=%s",
            number, status, company_id, container_type,
        )
        return cursor.lastrowid


async def set_arrived(container_id: int) -> None:
    """Устанавливает статус on_terminal и дату прибытия."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as conn:
        await conn.execute(
            "UPDATE containers SET status='on_terminal', arrival_date=? WHERE id=?",
            (now, container_id),
        )
        await conn.commit()


async def set_departed(
    container_id: int, departure_date: str | None = None
) -> None:
    """Переводит контейнер в статус departed с указанной датой вывоза.

    Если ``departure_date`` не задан, подставляется текущий момент.
    Формат даты — строка в виде ``YYYY-MM-DD HH:MM:SS`` (как и в других
    местах), парсинг даты на клиенте обязан использовать тот же формат.
    """
    dt_str = departure_date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as conn:
        await conn.execute(
            "UPDATE containers SET status='departed', departure_date=? "
            "WHERE id=?",
            (dt_str, container_id),
        )
        await conn.commit()


async def update_departure_date(
    container_id: int, departure_date: str
) -> None:
    """Меняет только дату вывоза без перевода статуса.

    Используется для редактирования уже вывезенного контейнера.
    """
    async with get_db() as conn:
        await conn.execute(
            "UPDATE containers SET departure_date=? WHERE id=?",
            (departure_date, container_id),
        )
        await conn.commit()


async def undo_departure(container_id: int) -> None:
    """Отменяет вывоз: статус on_terminal, departure_date=NULL."""
    async with get_db() as conn:
        await conn.execute(
            "UPDATE containers SET status='on_terminal', departure_date=NULL WHERE id=?",
            (container_id,),
        )
        await conn.commit()


async def update_type(container_id: int, container_type: str) -> None:
    """Обновляет тип контейнера."""
    async with get_db() as conn:
        await conn.execute(
            "UPDATE containers SET type=? WHERE id=?", (container_type, container_id)
        )
        await conn.commit()


async def update_number(container_id: int, number: str, display_number: str) -> bool:
    """Обновляет номер контейнера. Возвращает False при дубликате."""
    try:
        async with get_db() as conn:
            await conn.execute(
                "UPDATE containers SET number=?, display_number=? WHERE id=?",
                (number, display_number, container_id),
            )
            await conn.commit()
            return True
    except aiosqlite.IntegrityError:
        return False


async def update_company(container_id: int, company_id: int) -> None:
    """Меняет компанию контейнера."""
    async with get_db() as conn:
        await conn.execute(
            "UPDATE containers SET company_id=? WHERE id=?", (company_id, container_id)
        )
        await conn.commit()


async def delete_container(container_id: int) -> None:
    """Удаляет контейнер."""
    async with get_db() as conn:
        await conn.execute("DELETE FROM containers WHERE id=?", (container_id,))
        await conn.commit()
    logger.info("Контейнер удалён: id=%s", container_id)


async def active_by_type(ctype: str) -> list[aiosqlite.Row]:
    """Активные контейнеры (on_terminal) заданного типа + имя компании.

    Сортировка и группировка по компании делается в хэндлере на Python,
    здесь только фильтрация + JOIN.
    """
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT c.id, c.display_number, c.arrival_date, "
                "c.company_id, co.name AS company_name "
                "FROM containers c "
                "LEFT JOIN companies co ON co.id = c.company_id "
                "WHERE c.status='on_terminal' AND c.type=?",
                (ctype,),
            )
        ).fetchall()


async def active_for_company(company_id: int) -> list[aiosqlite.Row]:
    """Активные контейнеры компании (on_terminal + in_transit)."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT * FROM containers "
                "WHERE company_id=? AND status IN ('on_terminal', 'in_transit') "
                "ORDER BY arrival_date DESC",
                (company_id,),
            )
        ).fetchall()


async def all_for_company(company_id: int) -> list[aiosqlite.Row]:
    """Все контейнеры компании."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT c.*, co.name AS company_name, "
                "co.entry_fee AS comp_entry_fee, "
                "co.free_days AS comp_free_days, "
                "co.storage_rate AS comp_storage_rate, "
                "co.storage_period_days AS comp_storage_period_days "
                "FROM containers c "
                "LEFT JOIN companies co ON co.id = c.company_id "
                "WHERE c.company_id=? ORDER BY c.arrival_date DESC",
                (company_id,),
            )
        ).fetchall()


async def departed_for_company(company_id: int) -> list[aiosqlite.Row]:
    """Вывезенные контейнеры компании."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT c.*, co.name AS company_name, "
                "co.entry_fee AS comp_entry_fee, "
                "co.free_days AS comp_free_days, "
                "co.storage_rate AS comp_storage_rate, "
                "co.storage_period_days AS comp_storage_period_days "
                "FROM containers c "
                "LEFT JOIN companies co ON co.id = c.company_id "
                "WHERE c.company_id=? AND c.status='departed' "
                "ORDER BY c.departure_date DESC",
                (company_id,),
            )
        ).fetchall()


async def all_containers() -> list[aiosqlite.Row]:
    """Все контейнеры с джойном компании (для общего отчёта)."""
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT c.*, co.name AS company_name, "
                "co.entry_fee AS comp_entry_fee, "
                "co.free_days AS comp_free_days, "
                "co.storage_rate AS comp_storage_rate, "
                "co.storage_period_days AS comp_storage_period_days "
                "FROM containers c "
                "LEFT JOIN companies co ON co.id = c.company_id "
                "ORDER BY c.company_id, c.arrival_date DESC"
            )
        ).fetchall()


async def fetch_for_report(
    statuses: tuple[str, ...],
    company_id: int | None = None,
) -> list[aiosqlite.Row]:
    """Выборка контейнеров для генератора отчётов.

    ``statuses`` — кортеж статусов, которые должны попасть в выдачу
    (например ``('on_terminal',)`` или ``('on_terminal','departed')``).
    ``company_id`` — если задан, выдача ограничивается одной компанией.
    Всегда JOIN'им таблицу компаний, чтобы получить ``company_name`` и
    индивидуальные тарифы для расчёта стоимости.
    """
    if not statuses:
        return []

    placeholders = ",".join("?" * len(statuses))
    sql = (
        "SELECT c.*, co.name AS company_name, "
        "co.entry_fee AS comp_entry_fee, "
        "co.free_days AS comp_free_days, "
        "co.storage_rate AS comp_storage_rate, "
        "co.storage_period_days AS comp_storage_period_days "
        "FROM containers c "
        "LEFT JOIN companies co ON co.id = c.company_id "
        f"WHERE c.status IN ({placeholders})"
    )
    params: list = list(statuses)
    if company_id is not None:
        sql += " AND c.company_id = ?"
        params.append(company_id)

    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (await conn.execute(sql, params)).fetchall()
