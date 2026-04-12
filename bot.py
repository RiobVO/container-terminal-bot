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
    dp = Dispatcher(storage=MemoryStorage())

    chat_filter = ChatFilterMiddleware(cfg.group_ids)
    dp.message.middleware(chat_filter)
    dp.callback_query.middleware(chat_filter)

    dp.message.middleware(RoleMiddleware())
    dp.callback_query.middleware(RoleMiddleware())

    setup_routers(dp)

    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск бота"),
        BotCommand(command="help", description="Как пользоваться ботом"),
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
    ])

    logger.info("Бот запущен")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
