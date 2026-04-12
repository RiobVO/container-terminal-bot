import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import load_config
from db import init_db
from handlers import setup_routers
from services.scheduler import init_scheduler
from middlewares.chat_filter import ChatFilterMiddleware
from middlewares.role import RoleMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = load_config()

    await init_db(
        path=cfg.db_path,
        admin_ids=cfg.admin_ids,
        default_entry_fee=cfg.default_entry_fee,
        default_free_days=cfg.default_free_days,
        default_storage_rate=cfg.default_storage_rate,
        default_storage_period_days=cfg.default_storage_period_days,
    )

    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    bot._group_ids = cfg.group_ids
    dp = Dispatcher(storage=MemoryStorage())

    chat_filter = ChatFilterMiddleware(cfg.group_ids)
    dp.message.middleware(chat_filter)
    dp.callback_query.middleware(chat_filter)

    dp.message.middleware(RoleMiddleware())
    dp.callback_query.middleware(RoleMiddleware())

    setup_routers(dp)

    # Планировщик отчётов (только если есть группы)
    if cfg.group_ids:
        try:
            scheduler = init_scheduler(
                bot=bot,
                group_ids=cfg.group_ids,
                report_hour=cfg.report_hour,
                evening_hour=cfg.evening_report_hour,
                timezone=cfg.timezone,
            )
            scheduler.start()
            logger.info(
                "Планировщик запущен: утренний=%02d:00, вечерний=%02d:00, tz=%s",
                cfg.report_hour, cfg.evening_report_hour, cfg.timezone,
            )
        except Exception:
            logger.exception(
                "Не удалось запустить планировщик (проверь TIMEZONE=%s)",
                cfg.timezone,
            )

    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск бота"),
        BotCommand(command="help", description="Как пользоваться ботом"),
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
        BotCommand(command="report", description="Отправить отчёт в канал"),
    ])

    logger.info("Бот запущен")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
