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


def load_config() -> Config:
    """Загружает конфигурацию из переменных окружения."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    raw_ids = os.getenv("ADMIN_IDS", "")
    admin_ids = frozenset(int(x) for x in raw_ids.split(",") if x.strip())
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
    )
