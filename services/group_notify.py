"""Отправка уведомлений в разрешённые группы."""
import asyncio
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def _send_one(
    bot: Bot,
    gid: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> None:
    """Отправка в одну группу с подавлением ошибок (бот удалён, нет прав)."""
    try:
        await bot.send_message(
            chat_id=gid,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception:
        logger.warning("Не удалось отправить в группу %s", gid, exc_info=True)


async def notify_groups(
    bot: Bot,
    group_ids: frozenset[int],
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Отправляет сообщение во все разрешённые группы параллельно.

    Раньше шла последовательная рассылка с await: на N групп вызывающий
    хэндлер блокировался на N × ~200 мс (на каждый Telegram API-запрос).
    После регистрации контейнера это давало юзеру видимый лаг 1–2 секунды
    между «выбрал тип» и готовностью бота к следующему действию.
    Теперь все send_message запускаются параллельно через gather,
    общее время = max задержка одной группы.
    """
    if not group_ids:
        return
    await asyncio.gather(
        *(_send_one(bot, gid, text, reply_markup) for gid in group_ids)
    )
