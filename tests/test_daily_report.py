"""Тесты формирования утреннего отчёта и предупреждений."""
from services.daily_report import _classify_warning, _format_money


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
