"""Тесты формирования утреннего/вечернего отчётов и персистенции снимка."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from db import companies as db_comp
from db import containers as db_cont
from services.daily_report import (
    _classify_warning,
    _format_money,
    _load_morning_snapshot,
    _save_morning_snapshot,
    _snapshot_path,
    build_evening_report,
    build_morning_report,
)


def _dt_str(days_ago: int) -> str:
    """Дата N дней назад в формате БД (с временем)."""
    return (datetime.now() - timedelta(days=days_ago)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def test_classify_warning_red():
    """Контейнер превысил free_days — 🔴."""
    level, days_left = _classify_warning(days_on_terminal=35, free_days=30)
    assert level == "red"
    assert days_left == -5


def test_classify_warning_yellow():
    """До тарификации 1-3 дня — 🟡."""
    level, days_left = _classify_warning(days_on_terminal=28, free_days=30)
    assert level == "yellow"
    assert days_left == 2


def test_classify_warning_green():
    """До тарификации 4-7 дней — 💚."""
    level, days_left = _classify_warning(days_on_terminal=24, free_days=30)
    assert level == "green"
    assert days_left == 6


def test_classify_warning_none():
    """Больше 7 дней до тарификации — None."""
    level, days_left = _classify_warning(days_on_terminal=10, free_days=30)
    assert level is None
    assert days_left == 20


def test_format_money():
    assert _format_money(1234.5) == "1 234.50"
    assert _format_money(0) == "0.00"


# --- Персистенция утреннего снимка ---


def test_snapshot_path_from_database_path(tmp_path, monkeypatch):
    """Снимок кладётся рядом с БД из DATABASE_PATH."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "container.db"))
    assert _snapshot_path() == tmp_path / "morning_snapshot.json"


def test_snapshot_path_fallback_db_path(tmp_path, monkeypatch):
    """Без DATABASE_PATH используется фолбэк DB_PATH."""
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "bot.db"))
    assert _snapshot_path() == tmp_path / "morning_snapshot.json"


def test_save_and_load_snapshot_roundtrip(tmp_path, monkeypatch):
    """Сохранённый снимок читается обратно с теми же значениями."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    ts = datetime(2026, 6, 10, 6, 0, 0)
    _save_morning_snapshot(
        {"on_terminal": 5, "total_debt": 123.45, "timestamp": ts}
    )

    loaded = _load_morning_snapshot()
    assert loaded == {"on_terminal": 5, "total_debt": 123.45, "timestamp": ts}


def test_load_snapshot_missing_file(tmp_path, monkeypatch):
    """Нет файла — None без ошибок."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    assert _load_morning_snapshot() is None


def test_load_snapshot_corrupted_file(tmp_path, monkeypatch, caplog):
    """Битый JSON — None и warning в лог."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    (tmp_path / "morning_snapshot.json").write_text(
        "{не json", encoding="utf-8"
    )

    with caplog.at_level("WARNING"):
        assert _load_morning_snapshot() is None
    assert "Не удалось прочитать утренний снимок" in caplog.text


def test_save_snapshot_failure_is_swallowed(tmp_path, monkeypatch, caplog):
    """Ошибка записи (нет каталога) не пробрасывается, только warning."""
    monkeypatch.setenv(
        "DATABASE_PATH", str(tmp_path / "no_such_dir" / "test.db")
    )
    with caplog.at_level("WARNING"):
        _save_morning_snapshot(
            {"on_terminal": 1, "total_debt": 0.0, "timestamp": datetime.now()}
        )
    assert "Не удалось сохранить утренний снимок" in caplog.text


# --- Утренний отчёт ---


async def test_morning_report_with_warnings(test_db, monkeypatch):
    """Все уровни предупреждений + в пути + вывезенные вчера."""
    monkeypatch.setenv("DATABASE_PATH", test_db)
    comp_id = await db_comp.add_company("Ромашка")

    # free_days по умолчанию 30: 35 дней — red, 28 — yellow, 24 — green
    await db_cont.add_container(
        "REDD1234567", "REDD 1234567", comp_id, "on_terminal", _dt_str(35)
    )
    await db_cont.add_container(
        "YELL1234567", "YELL 1234567", comp_id, "on_terminal", _dt_str(28)
    )
    await db_cont.add_container(
        "GREE1234567", "GREE 1234567", comp_id, "on_terminal", _dt_str(24)
    )
    await db_cont.add_container(
        "TRAN1234567", "TRAN 1234567", comp_id, "in_transit", None
    )

    yesterday = datetime.now() - timedelta(days=1)
    # Дата вывоза с временем — парсится первым форматом
    dep_full_id = await db_cont.add_container(
        "DEPA1234567", "DEPA 1234567", comp_id, "on_terminal", _dt_str(10)
    )
    await db_cont.set_departed(
        dep_full_id, yesterday.strftime("%Y-%m-%d %H:%M:%S")
    )
    # Дата вывоза без времени — первый формат падает, второй парсит
    dep_short_id = await db_cont.add_container(
        "DEPB1234567", "DEPB 1234567", comp_id, "on_terminal", _dt_str(10)
    )
    await db_cont.set_departed(dep_short_id, yesterday.strftime("%Y-%m-%d"))
    # Непарсимая дата вывоза — молча пропускается
    dep_bad_id = await db_cont.add_container(
        "DEPC1234567", "DEPC 1234567", comp_id, "on_terminal", _dt_str(10)
    )
    await db_cont.set_departed(dep_bad_id, "когда-то")

    text = await build_morning_report()

    assert "Утренний отчёт" in text
    assert "На терминале: 3 контейнеров" in text
    assert "В пути: 1 контейнеров" in text
    assert "Вывезено (вчера): 2" in text
    assert "ТАРИФИКАЦИЯ НАЧАЛАСЬ" in text
    assert "REDD 1234567 (Ромашка) — 5 дн. на тарификации" in text
    assert "Скоро тарификация" in text
    assert "YELL 1234567 (Ромашка) — через 2 дн." in text
    assert "Приближается тарификация" in text
    assert "GREE 1234567 (Ромашка) — через 6 дн." in text

    # Снимок сохранён рядом с тестовой БД
    snapshot = json.loads(
        (Path(test_db).parent / "morning_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    assert snapshot["on_terminal"] == 3
    assert snapshot["total_debt"] > 0


async def test_morning_report_no_warnings(test_db, monkeypatch):
    """Контейнеры далеко от тарификации — блок ✅."""
    monkeypatch.setenv("DATABASE_PATH", test_db)
    comp_id = await db_comp.add_company("Ромашка")
    await db_cont.add_container(
        "SAFE1234567", "SAFE 1234567", comp_id, "on_terminal", _dt_str(5)
    )

    text = await build_morning_report()

    assert "Нет контейнеров, приближающихся к тарификации" in text
    assert "ТАРИФИКАЦИЯ" not in text


# --- Вечерний отчёт ---


async def test_evening_report_with_morning_snapshot(test_db, monkeypatch):
    """Прибытия/вывозы за сегодня + diff с утренним снимком."""
    monkeypatch.setenv("DATABASE_PATH", test_db)
    comp_id = await db_comp.add_company("Ромашка")

    now = datetime.now()
    # Прибыл сегодня (дата с временем)
    await db_cont.add_container(
        "ARRA1234567", "ARRA 1234567", comp_id, "on_terminal",
        now.strftime("%Y-%m-%d %H:%M:%S"),
    )
    # Прибыл сегодня (дата без времени — второй формат парсинга)
    await db_cont.add_container(
        "ARRB1234567", "ARRB 1234567", comp_id, "on_terminal",
        now.strftime("%Y-%m-%d"),
    )
    # Непарсимая дата прибытия — пропускается без падения
    await db_cont.add_container(
        "ARRC1234567", "ARRC 1234567", comp_id, "in_transit", "не дата"
    )
    # Вывезен сегодня (с временем) — даёт выручку
    dep_a = await db_cont.add_container(
        "DEPA1234567", "DEPA 1234567", comp_id, "on_terminal", _dt_str(10)
    )
    await db_cont.set_departed(dep_a, now.strftime("%Y-%m-%d %H:%M:%S"))
    # Вывезен сегодня (без времени)
    dep_b = await db_cont.add_container(
        "DEPB1234567", "DEPB 1234567", comp_id, "on_terminal", _dt_str(10)
    )
    await db_cont.set_departed(dep_b, now.strftime("%Y-%m-%d"))

    # Утренний отчёт пишет снимок «сегодня» — вечером появится diff
    await build_morning_report()
    text = await build_evening_report()

    assert "Итоги дня" in text
    assert "Прибыло: +2 контейнеров" in text
    assert "Вывезено: -2 контейнеров" in text
    assert "📈 На терминале: 2 → 2 (+0)" in text


async def test_evening_report_without_snapshot(test_db, monkeypatch):
    """Нет снимка — без diff, только текущее число."""
    monkeypatch.setenv("DATABASE_PATH", test_db)

    text = await build_evening_report()

    assert "Прибыло: +0 контейнеров" in text
    assert "Вывезено: -0 контейнеров" in text
    assert "📈 На терминале: 0" in text
    assert "→" not in text


async def test_evening_report_stale_snapshot_ignored(test_db, monkeypatch):
    """Снимок от вчера не используется для diff."""
    monkeypatch.setenv("DATABASE_PATH", test_db)
    _save_morning_snapshot({
        "on_terminal": 7,
        "total_debt": 100.0,
        "timestamp": datetime.now() - timedelta(days=1),
    })

    text = await build_evening_report()

    assert "📈 На терминале: 0" in text
    assert "→" not in text
