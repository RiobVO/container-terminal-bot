"""Отправка уведомлений в разрешённые группы."""
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def notify_groups(
    bot: Bot,
    group_ids: frozenset[int],
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Отправляет сообщение во все разрешённые группы.

    Ошибки отправки (бот удалён, нет прав) логируются,
    но не блокируют основной флоу.
    """
    for gid in group_ids:
        try:
            await bot.send_message(
                chat_id=gid,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except Exception:
            logger.warning("Не удалось отправить в группу %s", gid, exc_info=True)
