"""Дополнительные тесты калькулятора: клампинг периода и парсинг дат.

Основной набор живёт в tests/test_calculator.py со своим раннером —
этот файл покрывает только ветки, не задетые там.
"""
from datetime import datetime

import pytest

from services.calculator import _parse_dt, calculate_container_cost


def test_storage_period_clamped_to_one():
    """period_days < 1 приводится к 1 — посуточная тарификация."""
    container = {
        "status": "departed",
        "arrival_date": "2026-01-01 10:00:00",
        "departure_date": "2026-02-10 10:00:00",  # 40 дней
    }
    result = calculate_container_cost(
        container,
        {"default_free_days": 30, "default_storage_rate": 2.0},
        comp_storage_period_days=0,
    )

    assert result["period_days"] == 1
    assert result["billable_days"] == 10
    # При периоде 1 день число периодов = billable_days
    assert result["periods"] == 10
    assert result["storage"] == 20.0


def test_parse_dt_date_only_format():
    """Дата без времени парсится вторым форматом."""
    assert _parse_dt("2026-01-15") == datetime(2026, 1, 15)


def test_parse_dt_invalid_raises():
    """Непарсимая строка — ValueError с текстом ошибки."""
    with pytest.raises(ValueError, match="Не удалось распарсить дату"):
        _parse_dt("15 января")
