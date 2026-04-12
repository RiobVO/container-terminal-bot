import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str
    admin_ids: frozenset[int]
    default_entry_fee: float
    default_free_days: int
    default_storage_rate: float
    default_storage_period_days: int
    group_ids: frozenset[int]
    report_hour: int
    evening_report_hour: int
    timezone: str
    redis_url: str
    backup_chat_id: int | None


def load_config() -> Config:
    """Загружает конфигурацию из переменных окружения."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не задан в .env")

    raw_ids = os.getenv("ADMIN_IDS", "")
    admin_ids = frozenset(int(x) for x in raw_ids.split(",") if x.strip())
    if not admin_ids:
        logger.warning("ADMIN_IDS пуст — ни один пользователь не получит роль admin")

    raw_group_ids = os.getenv("GROUP_IDS", "")
    group_ids = frozenset(int(x) for x in raw_group_ids.split(",") if x.strip())

    report_hour = int(os.getenv("REPORT_HOUR", "6"))
    evening_report_hour = int(os.getenv("EVENING_REPORT_HOUR", "20"))
    if not 0 <= report_hour <= 23:
        raise ValueError(f"REPORT_HOUR должен быть 0–23, получено {report_hour}")
    if not 0 <= evening_report_hour <= 23:
        raise ValueError(f"EVENING_REPORT_HOUR должен быть 0–23, получено {evening_report_hour}")

    raw_backup = os.getenv("BACKUP_CHAT_ID", "").strip()
    backup_chat_id = None
    if raw_backup:
        try:
            backup_chat_id = int(raw_backup)
        except ValueError:
            raise ValueError(f"BACKUP_CHAT_ID должен быть числом, получено '{raw_backup}'")

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
        report_hour=report_hour,
        evening_report_hour=evening_report_hour,
        timezone=os.getenv("TIMEZONE", "Asia/Tashkent"),
        redis_url=os.getenv("REDIS_URL", ""),
        backup_chat_id=backup_chat_id,
    )
