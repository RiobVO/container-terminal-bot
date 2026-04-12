import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str
    admin_ids: frozenset[int]
    default_entry_fee: float
    default_free_days: int
    default_storage_rate: float
    default_storage_period_days: int
    # Группы Telegram, которым разрешена работа с ботом
    group_ids: frozenset[int]
    # Часы отправки утреннего и вечернего отчётов
    report_hour: int
    evening_report_hour: int
    # Временная зона планировщика (APScheduler)
    timezone: str
    # Redis URL для хранения FSM (пустая строка = MemoryStorage)
    redis_url: str


def load_config() -> Config:
    """Загружает конфигурацию из переменных окружения."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    raw_ids = os.getenv("ADMIN_IDS", "")
    admin_ids = frozenset(int(x) for x in raw_ids.split(",") if x.strip())
    raw_group_ids = os.getenv("GROUP_IDS", "")
    group_ids = frozenset(int(x) for x in raw_group_ids.split(",") if x.strip())
    return Config(
        bot_token=token,
        db_path=os.getenv("DATABASE_PATH") or os.getenv("DB_PATH", "bot.db"),
        admin_ids=admin_ids,
        default_entry_fee=float(os.getenv("DEFAULT_ENTRY_FEE", "20")),
        default_free_days=int(os.getenv("DEFAULT_FREE_DAYS", "30")),
        default_storage_rate=float(os.getenv("DEFAULT_STORAGE_RATE", "20")),
        default_storage_period_days=int(
            os.getenv("DEFAULT_STORAGE_PERIOD_DAYS", "30")
        ),
        group_ids=group_ids,
        report_hour=int(os.getenv("REPORT_HOUR", "6")),
        evening_report_hour=int(os.getenv("EVENING_REPORT_HOUR", "20")),
        timezone=os.getenv("TIMEZONE", "Asia/Tashkent"),
        redis_url=os.getenv("REDIS_URL", ""),
    )
