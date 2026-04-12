"""Планировщик автоматических отчётов и бэкапов."""
import logging
import shutil
from datetime import datetime
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.daily_report import build_morning_report, build_evening_report
from services.group_notify import notify_groups

logger = logging.getLogger(__name__)

# ID последнего закреплённого сообщения per group
_pinned_messages: dict[int, int] = {}


def _morning_keyboard() -> InlineKeyboardMarkup:
    """Inline-кнопки под утренним отчётом."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 По компаниям", callback_data="morning:companies"),
            InlineKeyboardButton(text="⚠️ Предупреждения", callback_data="morning:warnings"),
        ],
        [
            InlineKeyboardButton(text="📥 Скачать xlsx", callback_data="morning:xlsx"),
        ],
    ])


async def _send_morning_report(bot: Bot, group_ids: frozenset[int]) -> None:
    """Отправляет утренний отчёт и закрепляет его."""
    text = await build_morning_report()
    kb = _morning_keyboard()

    for gid in group_ids:
        try:
            prev_msg_id = _pinned_messages.get(gid)
            if prev_msg_id:
                try:
                    await bot.unpin_chat_message(chat_id=gid, message_id=prev_msg_id)
                except Exception:
                    pass

            msg = await bot.send_message(
                chat_id=gid, text=text, parse_mode="HTML", reply_markup=kb,
            )

            try:
                await bot.pin_chat_message(
                    chat_id=gid, message_id=msg.message_id, disable_notification=True,
                )
                _pinned_messages[gid] = msg.message_id
            except Exception:
                logger.warning("Не удалось закрепить отчёт в группе %s", gid)

        except Exception:
            logger.warning("Не удалось отправить утренний отчёт в %s", gid, exc_info=True)


async def _send_evening_report(bot: Bot, group_ids: frozenset[int]) -> None:
    """Отправляет вечерний итог дня."""
    text = await build_evening_report()
    await notify_groups(bot, group_ids, text)


async def _backup_db(bot: Bot, backup_chat_id: int, db_path: str) -> None:
    """Копирует БД и отправляет в канал бэкапов."""
    src = Path(db_path)
    if not src.exists():
        logger.warning("БД не найдена для бэкапа: %s", db_path)
        return

    # Локальная копия
    backup_dir = src.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_name = f"{src.stem}_{ts}{src.suffix}"
    backup_path = backup_dir / backup_name
    shutil.copy2(src, backup_path)
    logger.info("Локальный бэкап: %s", backup_path)

    # Ротация: удаляем локальные бэкапы старше 7 дней
    for old in sorted(backup_dir.glob(f"{src.stem}_*{src.suffix}")):
        if old == backup_path:
            continue
        try:
            name_part = old.stem.replace(f"{src.stem}_", "")
            file_dt = datetime.strptime(name_part, "%Y-%m-%d_%H-%M")
            if (datetime.now() - file_dt).days > 7:
                old.unlink()
                logger.info("Удалён старый бэкап: %s", old.name)
        except (ValueError, OSError):
            continue

    # Отправляем в канал бэкапов
    try:
        await bot.send_document(
            chat_id=backup_chat_id,
            document=FSInputFile(backup_path, filename=backup_name),
            caption=f"💾 Бэкап БД — {ts}",
        )
        logger.info("Бэкап отправлен в канал %s", backup_chat_id)
    except Exception:
        logger.warning("Не удалось отправить бэкап в канал %s", backup_chat_id, exc_info=True)


def init_scheduler(
    bot: Bot,
    group_ids: frozenset[int],
    report_hour: int,
    evening_hour: int,
    timezone: str,
    backup_chat_id: int | None = None,
    db_path: str = "",
) -> AsyncIOScheduler:
    """Создаёт и возвращает настроенный планировщик."""
    scheduler = AsyncIOScheduler(timezone=timezone)

    scheduler.add_job(
        _send_morning_report,
        CronTrigger(hour=report_hour, minute=0),
        args=[bot, group_ids],
        id="morning_report",
        name="Утренний отчёт",
    )

    scheduler.add_job(
        _send_evening_report,
        CronTrigger(hour=evening_hour, minute=0),
        args=[bot, group_ids],
        id="evening_report",
        name="Вечерний итог дня",
    )

    # Бэкап БД каждые 6 часов (03:00, 09:00, 15:00, 21:00)
    if backup_chat_id and db_path:
        scheduler.add_job(
            _backup_db,
            CronTrigger(hour="3,9,15,21", minute=0),
            args=[bot, backup_chat_id, db_path],
            id="db_backup",
            name="Бэкап БД",
        )

    return scheduler
