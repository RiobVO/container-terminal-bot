"""Тесты load_config: дефолты и ветки валидации env-переменных."""
import pytest

from config import load_config

# Все переменные, которые читает load_config, — чистим перед каждым тестом,
# чтобы реальный .env не влиял на результат.
_ENV_KEYS = [
    "BOT_TOKEN",
    "ADMIN_IDS",
    "GROUP_IDS",
    "REPORT_HOUR",
    "EVENING_REPORT_HOUR",
    "BACKUP_CHAT_ID",
    "DATABASE_PATH",
    "DB_PATH",
    "DEFAULT_ENTRY_FEE",
    "DEFAULT_FREE_DAYS",
    "DEFAULT_STORAGE_RATE",
    "DEFAULT_STORAGE_PERIOD_DAYS",
    "TIMEZONE",
    "REDIS_URL",
]


@pytest.fixture
def clean_env(monkeypatch):
    """Чистое окружение с минимально необходимым BOT_TOKEN."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BOT_TOKEN", "42:TEST-TOKEN")
    return monkeypatch


def test_defaults(clean_env):
    """Только BOT_TOKEN — всё остальное из дефолтов."""
    cfg = load_config()
    assert cfg.bot_token == "42:TEST-TOKEN"
    assert cfg.db_path == "bot.db"
    assert cfg.admin_ids == frozenset()
    assert cfg.group_ids == frozenset()
    assert cfg.default_entry_fee == 20.0
    assert cfg.default_free_days == 30
    assert cfg.default_storage_rate == 20.0
    assert cfg.default_storage_period_days == 30
    assert cfg.report_hour == 6
    assert cfg.evening_report_hour == 20
    assert cfg.timezone == "Asia/Tashkent"
    assert cfg.redis_url == ""
    assert cfg.backup_chat_id is None


def test_missing_bot_token(clean_env):
    clean_env.delenv("BOT_TOKEN")
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        load_config()


def test_admin_and_group_ids_parsed(clean_env):
    clean_env.setenv("ADMIN_IDS", "111, 222")
    clean_env.setenv("GROUP_IDS", "-1001234567890")
    cfg = load_config()
    assert cfg.admin_ids == frozenset({111, 222})
    assert cfg.group_ids == frozenset({-1001234567890})


def test_report_hour_out_of_range(clean_env):
    clean_env.setenv("REPORT_HOUR", "24")
    with pytest.raises(ValueError, match="REPORT_HOUR"):
        load_config()


def test_evening_report_hour_out_of_range(clean_env):
    clean_env.setenv("EVENING_REPORT_HOUR", "-1")
    with pytest.raises(ValueError, match="EVENING_REPORT_HOUR"):
        load_config()


def test_backup_chat_id_valid(clean_env):
    clean_env.setenv("BACKUP_CHAT_ID", "-1009876543210")
    cfg = load_config()
    assert cfg.backup_chat_id == -1009876543210


def test_backup_chat_id_not_a_number(clean_env):
    clean_env.setenv("BACKUP_CHAT_ID", "abc")
    with pytest.raises(ValueError, match="BACKUP_CHAT_ID"):
        load_config()


def test_db_path_fallback(clean_env):
    """DATABASE_PATH приоритетнее DB_PATH."""
    clean_env.setenv("DB_PATH", "fallback.db")
    assert load_config().db_path == "fallback.db"
    clean_env.setenv("DATABASE_PATH", "primary.db")
    assert load_config().db_path == "primary.db"
