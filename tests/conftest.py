import pytest

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
