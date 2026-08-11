"""Тесты services/scheduler.py: отчёты, бэкап БД, heartbeat, регистрация джобов."""
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import scheduler as sched
from services.scheduler import (
    _backup_db,
    _morning_keyboard,
    _send_evening_report,
    _send_morning_report,
    _split_for_telegram,
    _touch_heartbeat,
    init_scheduler,
)

GID = -100123
GROUPS = frozenset({GID})


@pytest.fixture(autouse=True)
def clear_pinned():
    """Модульный кэш закреплённых сообщений не должен течь между тестами."""
    sched._pinned_messages.clear()
    yield
    sched._pinned_messages.clear()


def _make_bot(message_id: int = 7) -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=message_id))
    bot.unpin_chat_message = AsyncMock()
    bot.pin_chat_message = AsyncMock()
    bot.send_document = AsyncMock()
    return bot


# ---------- _morning_keyboard ----------

def test_morning_keyboard_layout():
    kb = _morning_keyboard()
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert callbacks == ["morning:companies", "morning:warnings", "morning:xlsx"]


# ---------- _split_for_telegram ----------

def test_split_short_text_single_chunk():
    assert _split_for_telegram("короткий текст") == ["короткий текст"]


def test_split_by_lines():
    """Строки склеиваются до лимита, переполнение уходит в новый кусок."""
    chunks = _split_for_telegram("aaaa\nbbbb\ncccc", limit=10)
    assert chunks == ["aaaa\nbbbb", "cccc"]


def test_split_overlong_line_after_text():
    """Сверхдлинная строка сбрасывает накопленное и режется по символам."""
    chunks = _split_for_telegram("ab\n" + "x" * 25, limit=10)
    assert chunks == ["ab", "x" * 10, "x" * 10, "x" * 5]


def test_split_overlong_line_first():
    """Сверхдлинная строка в начале — без пустого куска перед ней."""
    chunks = _split_for_telegram("x" * 25 + "\nab", limit=10)
    assert chunks == ["x" * 10, "x" * 10, "x" * 5, "ab"]


# ---------- _send_morning_report ----------

async def test_morning_report_sent_and_pinned():
    """Первая отправка: сообщение ушло, закрепилось, id запомнен."""
    bot = _make_bot(message_id=7)
    with patch(
        "services.scheduler.build_morning_report",
        new=AsyncMock(return_value="отчёт"),
    ):
        await _send_morning_report(bot, GROUPS)

    bot.unpin_chat_message.assert_not_awaited()
    bot.send_message.assert_awaited_once()
    assert bot.send_message.call_args.kwargs["chat_id"] == GID
    bot.pin_chat_message.assert_awaited_once_with(
        chat_id=GID, message_id=7, disable_notification=True,
    )
    assert sched._pinned_messages[GID] == 7


async def test_morning_report_unpins_previous():
    """Предыдущий закреп снимается перед новым."""
    sched._pinned_messages[GID] = 3
    bot = _make_bot(message_id=8)
    with patch(
        "services.scheduler.build_morning_report",
        new=AsyncMock(return_value="отчёт"),
    ):
        await _send_morning_report(bot, GROUPS)

    bot.unpin_chat_message.assert_awaited_once_with(chat_id=GID, message_id=3)
    assert sched._pinned_messages[GID] == 8


async def test_morning_report_unpin_error_logged(caplog):
    """Ошибка unpin (закреп уже снят руками) логируется и не мешает отправке."""
    sched._pinned_messages[GID] = 3
    bot = _make_bot()
    bot.unpin_chat_message.side_effect = Exception("message to unpin not found")
    with patch(
        "services.scheduler.build_morning_report",
        new=AsyncMock(return_value="отчёт"),
    ), caplog.at_level("ERROR", logger="services.scheduler"):
        await _send_morning_report(bot, GROUPS)

    bot.send_message.assert_awaited_once()
    bot.pin_chat_message.assert_awaited_once()
    assert any("не удалось снять закреп" in r.message for r in caplog.records)


async def test_morning_report_multipart():
    """Длинный отчёт уходит несколькими сообщениями, закрепляется первое."""
    long_text = "\n".join("строка " + "x" * 90 for _ in range(60))
    assert len(long_text) > sched._TG_MSG_LIMIT
    bot = _make_bot(message_id=9)
    with patch(
        "services.scheduler.build_morning_report",
        new=AsyncMock(return_value=long_text),
    ):
        await _send_morning_report(bot, GROUPS)

    assert bot.send_message.await_count >= 2
    bot.pin_chat_message.assert_awaited_once_with(
        chat_id=GID, message_id=9, disable_notification=True,
    )


async def test_morning_report_extra_part_error_logged(caplog):
    """Ошибка на продолжении логируется и не срывает закрепление первого сообщения."""
    long_text = "\n".join("строка " + "x" * 90 for _ in range(60))
    bot = _make_bot()
    first_msg = MagicMock(message_id=5)
    bot.send_message = AsyncMock(side_effect=[first_msg, Exception("flood")])
    with patch(
        "services.scheduler.build_morning_report",
        new=AsyncMock(return_value=long_text),
    ), caplog.at_level("ERROR", logger="services.scheduler"):
        await _send_morning_report(bot, GROUPS)

    bot.pin_chat_message.assert_awaited_once_with(
        chat_id=GID, message_id=5, disable_notification=True,
    )
    assert any("продолжение" in r.message for r in caplog.records)


async def test_morning_report_pin_error_logged(caplog):
    """Ошибка pin (нет прав) — отчёт отправлен, id не запоминается, ошибка в логе."""
    bot = _make_bot()
    bot.pin_chat_message.side_effect = Exception("not enough rights")
    with patch(
        "services.scheduler.build_morning_report",
        new=AsyncMock(return_value="отчёт"),
    ), caplog.at_level("ERROR", logger="services.scheduler"):
        await _send_morning_report(bot, GROUPS)

    assert GID not in sched._pinned_messages
    assert any("не удалось закрепить" in r.message for r in caplog.records)


async def test_morning_report_send_error_does_not_stop_other_groups(caplog):
    """Ошибка отправки в одну группу логируется и не валит остальные группы."""
    failing_gid = -100999
    bot = _make_bot(message_id=11)

    async def send(chat_id, **kwargs):
        if chat_id == failing_gid:
            raise Exception("bot was kicked")
        return MagicMock(message_id=11)

    bot.send_message = AsyncMock(side_effect=send)
    with patch(
        "services.scheduler.build_morning_report",
        new=AsyncMock(return_value="отчёт"),
    ), caplog.at_level("ERROR", logger="services.scheduler"):
        await _send_morning_report(bot, frozenset({GID, failing_gid}))

    # Здоровая группа получила отчёт и закреп, упавшая — попала в лог
    bot.pin_chat_message.assert_awaited_once_with(
        chat_id=GID, message_id=11, disable_notification=True,
    )
    assert failing_gid not in sched._pinned_messages
    assert any("не удалось отправить в группу" in r.message for r in caplog.records)


# ---------- _send_evening_report ----------

async def test_evening_report_notifies_groups():
    bot = _make_bot()
    with patch(
        "services.scheduler.build_evening_report",
        new=AsyncMock(return_value="итоги"),
    ), patch(
        "services.scheduler.notify_groups", new=AsyncMock()
    ) as notify:
        await _send_evening_report(bot, GROUPS)

    notify.assert_awaited_once_with(bot, GROUPS, "итоги")


# ---------- _backup_db ----------

async def test_backup_missing_db(tmp_path):
    """БД нет — джоба молча выходит, ничего не шлёт."""
    bot = _make_bot()
    await _backup_db(bot, backup_chat_id=-1009, db_path=str(tmp_path / "nope.db"))
    bot.send_document.assert_not_awaited()


async def test_backup_copies_and_sends(tmp_path):
    """Копия в data/backups + документ в канал."""
    db = tmp_path / "container.db"
    db.write_bytes(b"sqlite-data")
    bot = _make_bot()

    await _backup_db(bot, backup_chat_id=-1009, db_path=str(db))

    backups = list((tmp_path / "backups").glob("container_*.db"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"sqlite-data"
    bot.send_document.assert_awaited_once()
    assert bot.send_document.call_args.kwargs["chat_id"] == -1009


async def test_backup_rotation(tmp_path):
    """Бэкапы старше 7 дней удаляются, свежие и «битые» имена остаются."""
    db = tmp_path / "container.db"
    db.write_bytes(b"sqlite-data")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    old_ts = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d_%H-%M")
    fresh_ts = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d_%H-%M")
    old_file = backup_dir / f"container_{old_ts}.db"
    fresh_file = backup_dir / f"container_{fresh_ts}.db"
    junk_file = backup_dir / "container_garbage.db"  # не парсится strptime
    for f in (old_file, fresh_file, junk_file):
        f.write_bytes(b"old")

    bot = _make_bot()
    await _backup_db(bot, backup_chat_id=-1009, db_path=str(db))

    assert not old_file.exists()
    assert fresh_file.exists()
    assert junk_file.exists()


async def test_backup_send_error_logged(tmp_path):
    """Ошибка отправки в канал не валит джобу, локальная копия остаётся."""
    db = tmp_path / "container.db"
    db.write_bytes(b"sqlite-data")
    bot = _make_bot()
    bot.send_document.side_effect = Exception("chat not found")

    await _backup_db(bot, backup_chat_id=-1009, db_path=str(db))

    assert len(list((tmp_path / "backups").glob("container_*.db"))) == 1


# ---------- _touch_heartbeat ----------

def test_heartbeat_creates_file_near_db(tmp_path):
    """Файл heartbeat создаётся в каталоге БД."""
    db = tmp_path / "container.db"
    _touch_heartbeat(str(db))
    assert (tmp_path / "heartbeat").exists()


def test_heartbeat_updates_mtime(tmp_path):
    """Повторный вызов обновляет mtime существующего файла."""
    hb = tmp_path / "heartbeat"
    hb.touch()
    os.utime(hb, (0, 0))

    _touch_heartbeat(str(tmp_path / "container.db"))

    assert hb.stat().st_mtime > 0


def test_heartbeat_write_error_logged(tmp_path, caplog):
    """Ошибка записи — warning в лог, исключение не пробрасывается."""
    with patch(
        "services.scheduler.Path.touch", side_effect=OSError("read-only fs"),
    ), caplog.at_level("WARNING", logger="services.scheduler"):
        _touch_heartbeat(str(tmp_path / "container.db"))

    assert any("heartbeat" in r.message for r in caplog.records)


# ---------- init_scheduler ----------

def test_init_scheduler_with_backup():
    """С backup_chat_id и db_path регистрируются все четыре джобы."""
    scheduler = init_scheduler(
        bot=_make_bot(),
        group_ids=GROUPS,
        report_hour=6,
        evening_hour=20,
        timezone="Asia/Tashkent",
        backup_chat_id=-1009,
        db_path="data/container.db",
    )
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"morning_report", "evening_report", "db_backup", "heartbeat"}


def test_init_scheduler_without_backup():
    """Без backup_chat_id и db_path остаются только отчёты."""
    scheduler = init_scheduler(
        bot=_make_bot(),
        group_ids=GROUPS,
        report_hour=6,
        evening_hour=20,
        timezone="Asia/Tashkent",
    )
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"morning_report", "evening_report"}


def test_init_scheduler_heartbeat_without_backup():
    """db_path без backup_chat_id — heartbeat есть, бэкапа нет."""
    scheduler = init_scheduler(
        bot=_make_bot(),
        group_ids=GROUPS,
        report_hour=6,
        evening_hour=20,
        timezone="Asia/Tashkent",
        db_path="data/container.db",
    )
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"morning_report", "evening_report", "heartbeat"}


def test_init_scheduler_heartbeat_interval():
    """Heartbeat тикает раз в 60 секунд."""
    scheduler = init_scheduler(
        bot=_make_bot(),
        group_ids=GROUPS,
        report_hour=6,
        evening_hour=20,
        timezone="Asia/Tashkent",
        db_path="data/container.db",
    )
    job = scheduler.get_job("heartbeat")
    assert job.trigger.interval.total_seconds() == 60


def test_init_scheduler_backup_daily():
    """Бэкап БД идёт раз в сутки в 03:00."""
    scheduler = init_scheduler(
        bot=_make_bot(),
        group_ids=GROUPS,
        report_hour=6,
        evening_hour=20,
        timezone="Asia/Tashkent",
        backup_chat_id=-1009,
        db_path="data/container.db",
    )
    job = scheduler.get_job("db_backup")
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "3"
    assert fields["minute"] == "0"
