import os

# Пакет handlers/ выполняет load_config() на import-time
# (handlers/start.py, handlers/settings.py) — токен нужен до импорта
# тестовых модулей. setdefault не перетирает реальный .env.
os.environ.setdefault("BOT_TOKEN", "42:TEST-TOKEN")

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from db import init_db


@pytest.fixture
async def test_db(tmp_path):
    """Инициализирует тестовую БД во временном файле."""
    db_path = str(tmp_path / "test.db")
    await init_db(
        path=db_path,
        admin_ids=frozenset({111111}),
        default_entry_fee=20.0,
        default_free_days=30,
        default_storage_rate=20.0,
        default_storage_period_days=30,
    )
    yield db_path


@pytest.fixture
def make_message():
    """Фабрика mock-сообщений для прямого вызова хендлеров."""

    def _make(text: str = "") -> MagicMock:
        msg = MagicMock(spec=Message)
        msg.text = text
        msg.answer = AsyncMock()
        user = MagicMock()
        user.id = 111111  # admin из test_db (роль full)
        user.username = "operator"
        user.full_name = "Operator"
        msg.from_user = user
        bot = MagicMock()
        bot._group_ids = frozenset()  # выключает live-ленту в _finalize
        msg.bot = bot
        return msg

    return _make


@pytest.fixture
def fsm_state():
    """Настоящий FSMContext поверх MemoryStorage."""
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=1, user_id=111111),
    )
