"""Юнит-тесты для services.calculator.calculate_container_cost.

Запуск: `.venv/bin/python -m tests.test_calculator` (или через pytest, если
установлен). Без внешних зависимостей — ассерты и print для результатов.
"""
from datetime import datetime, timedelta

from services.calculator import calculate_container_cost


DEFAULT_SETTINGS = {
    "default_entry_fee": 20.0,
    "default_free_days": 30,
    "default_storage_rate": 20.0,
    "default_storage_period_days": 30,
}


def _days_ago(n: int) -> str:
    """Возвращает дату N дней назад в формате БД."""
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d %H:%M:%S")


def _container(status: str, arrival=None, departure=None) -> dict:
    return {
        "status": status,
        "arrival_date": arrival,
        "departure_date": departure,
    }


def test_daily_rate_with_free_days():
    """Ежедневный тариф: 45 дней хранения, 30 бесплатных, 15 платных дней × 0.5$."""
    c = _container("on_terminal", arrival=_days_ago(45))
    cost = calculate_container_cost(
        c, DEFAULT_SETTINGS,
        comp_entry_fee=10.0,
        comp_free_days=30,
        comp_storage_rate=0.5,
        comp_storage_period_days=1,
    )
    assert cost["days"] == 45, cost
    assert cost["billable_days"] == 15, cost
    assert cost["periods"] == 15, cost
    assert cost["period_days"] == 1, cost
    assert cost["storage"] == 7.5, cost
    assert cost["entry"] == 10.0, cost
    assert cost["total"] == 17.5, cost
    print("  ✓ daily rate with free days")


def test_monthly_rate_ceil():
    """Ежемесячный тариф: 65 дней, 30 бесплатных → 35 платных → ceil(35/30)=2 месяца."""
    c = _container("on_terminal", arrival=_days_ago(65))
    cost = calculate_container_cost(
        c, DEFAULT_SETTINGS,
        comp_entry_fee=15.0,
        comp_free_days=30,
        comp_storage_rate=20.0,
        comp_storage_period_days=30,
    )
    assert cost["days"] == 65, cost
    assert cost["billable_days"] == 35, cost
    assert cost["periods"] == 2, cost
    assert cost["period_days"] == 30, cost
    assert cost["storage"] == 40.0, cost
    assert cost["total"] == 55.0, cost
    print("  ✓ monthly rate with ceil")


def test_within_free_days():
    """Внутри бесплатного периода: платных дней и стоимости хранения нет."""
    c = _container("on_terminal", arrival=_days_ago(20))
    cost = calculate_container_cost(
        c, DEFAULT_SETTINGS,
        comp_entry_fee=20.0,
        comp_free_days=30,
        comp_storage_rate=20.0,
        comp_storage_period_days=30,
    )
    assert cost["days"] == 20, cost
    assert cost["billable_days"] == 0, cost
    assert cost["periods"] == 0, cost
    assert cost["storage"] == 0.0, cost
    assert cost["total"] == 20.0, cost
    print("  ✓ within free days window")


def test_in_transit_zero():
    """Контейнер в пути — всё нулевое."""
    c = _container("in_transit", arrival=None)
    cost = calculate_container_cost(
        c, DEFAULT_SETTINGS,
        comp_entry_fee=15.0,
        comp_free_days=30,
        comp_storage_rate=20.0,
        comp_storage_period_days=30,
    )
    assert cost["days"] == 0, cost
    assert cost["billable_days"] == 0, cost
    assert cost["periods"] == 0, cost
    assert cost["total"] == 0.0, cost
    print("  ✓ in_transit returns zeros")


def test_defaults_when_company_null():
    """Когда у компании все поля None — применяются defaults из settings."""
    c = _container("on_terminal", arrival=_days_ago(40))
    cost = calculate_container_cost(c, DEFAULT_SETTINGS)
    # 40 дней - 30 default_free_days = 10 platnyh -> ceil(10/30) = 1 период по 20$
    assert cost["entry"] == 20.0, cost
    assert cost["free_days"] == 30, cost
    assert cost["storage_rate"] == 20.0, cost
    assert cost["period_days"] == 30, cost
    assert cost["billable_days"] == 10, cost
    assert cost["periods"] == 1, cost
    assert cost["storage"] == 20.0, cost
    assert cost["total"] == 40.0, cost
    assert not cost["entry_is_custom"]
    assert not cost["free_days_is_custom"]
    print("  ✓ defaults applied when company params are None")


def test_departed_uses_departure_date():
    """Для вывезенного — end = departure_date, не сегодня."""
    arrival = _days_ago(100)
    departure = _days_ago(50)  # 50 дней хранения
    c = _container("departed", arrival=arrival, departure=departure)
    cost = calculate_container_cost(
        c, DEFAULT_SETTINGS,
        comp_entry_fee=10.0,
        comp_free_days=10,
        comp_storage_rate=1.0,
        comp_storage_period_days=1,
    )
    assert cost["days"] == 50, cost
    assert cost["billable_days"] == 40, cost
    assert cost["periods"] == 40, cost
    assert cost["storage"] == 40.0, cost
    assert cost["total"] == 50.0, cost
    print("  ✓ departed uses departure_date as end")


def _run_all():
    tests = [
        test_daily_rate_with_free_days,
        test_monthly_rate_ceil,
        test_within_free_days,
        test_in_transit_zero,
        test_defaults_when_company_null,
        test_departed_uses_departure_date,
    ]
    print(f"Running {len(tests)} tests…")
    for t in tests:
        t()
    print(f"All {len(tests)} tests passed.")


if __name__ == "__main__":
    _run_all()
