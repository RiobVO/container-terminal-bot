"""Append-only аудит-лог операций: кто, когда, что сделал.

Записи нужны для разборов спорных ситуаций по деньгам, поэтому
entity_label хранит читаемый идентификатор (номер контейнера, имя
компании) — лог остаётся понятным даже после удаления сущности.
"""
import logging
from datetime import datetime

import aiosqlite

from db import get_db

logger = logging.getLogger(__name__)


def actor_name_from(actor) -> str:
    """Читаемое имя актора: full_name → @username → tg_id → «?».

    ``actor`` — aiogram User или совместимый объект; None допустим.
    """
    if actor is None:
        return "?"
    if getattr(actor, "full_name", None):
        return actor.full_name
    if getattr(actor, "username", None):
        return f"@{actor.username}"
    return str(actor.id)


async def add_entry(
    actor,
    action: str,
    entity_type: str,
    entity_id: int | None,
    entity_label: str | None,
    details: str | None = None,
) -> None:
    """Пишет запись аудита. ``actor`` — message.from_user.

    Сбой записи никогда не пробрасывается: аудит вторичен по отношению
    к самой операции, потеря одной записи лога лучше сломанной
    бизнес-операции. Ошибка уходит в лог с контекстом.
    """
    try:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO audit_log "
                "(created_at, actor_tg_id, actor_name, action, "
                "entity_type, entity_id, entity_label, details) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    created_at,
                    actor.id if actor else None,
                    actor_name_from(actor),
                    action,
                    entity_type,
                    entity_id,
                    entity_label,
                    details,
                ),
            )
            await conn.commit()
    except Exception:
        logger.exception(
            "Сбой записи аудита: action=%s entity=%s/%s",
            action, entity_type, entity_id,
        )


async def list_for_container(
    number: str, limit: int = 15
) -> list[aiosqlite.Row]:
    """Последние записи аудита по контейнеру (новые сверху).

    Ключ записей — id контейнера (номер могут менять), поэтому номер
    сначала резолвится в id подзапросом.
    """
    async with get_db() as conn:
        conn.row_factory = aiosqlite.Row
        return await (
            await conn.execute(
                "SELECT * FROM audit_log "
                "WHERE entity_type='container' AND entity_id="
                "(SELECT id FROM containers WHERE number=?) "
                "ORDER BY id DESC LIMIT ?",
                (number, limit),
            )
        ).fetchall()
