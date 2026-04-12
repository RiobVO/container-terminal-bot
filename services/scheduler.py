"""Планировщик автоматических отчётов."""
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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


def init_scheduler(
    bot: Bot,
    group_ids: frozenset[int],
    report_hour: int,
    evening_hour: int,
    timezone: str,
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

    return scheduler
