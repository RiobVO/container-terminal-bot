"""Формирование текстов утреннего и вечернего отчётов."""
import logging
from datetime import datetime, timedelta

from db import containers as db_cont
from db.settings import get_all_settings
from services.calculator import calculate_container_cost

logger = logging.getLogger(__name__)

# Снимок утреннего состояния для сравнения в вечернем отчёте
_morning_snapshot: dict | None = None


def _format_money(value: float) -> str:
    """Форматирует число как '1 234.50'."""
    integer = int(value)
    frac = round(value - integer, 2)
    formatted_int = f"{integer:,}".replace(",", " ")
    return f"{formatted_int}.{int(frac * 100):02d}"


def _classify_warning(
    days_on_terminal: int, free_days: int
) -> tuple[str | None, int]:
    """Классифицирует уровень предупреждения.

    Возвращает (level, days_remaining).
    level: 'red' | 'yellow' | 'green' | None
    days_remaining: отрицательное = тарификация уже идёт N дней
    """
    days_remaining = free_days - days_on_terminal
    if days_remaining < 0:
        return "red", days_remaining
    if days_remaining <= 3:
        return "yellow", days_remaining
    if days_remaining <= 7:
        return "green", days_remaining
    return None, days_remaining


async def build_morning_report() -> str:
    """Формирует текст утреннего отчёта со сводкой и предупреждениями."""
    global _morning_snapshot

    settings = await get_all_settings()
    counts = await db_cont.count_by_status()
    all_containers = await db_cont.all_containers()

    total_debt = 0.0
    warnings: dict[str, list[str]] = {"red": [], "yellow": [], "green": []}

    for c in all_containers:
        if c["status"] != "on_terminal":
            continue

        cost = calculate_container_cost(
            c, settings,
            comp_entry_fee=c["comp_entry_fee"],
            comp_free_days=c["comp_free_days"],
            comp_storage_rate=c["comp_storage_rate"],
            comp_storage_period_days=c["comp_storage_period_days"],
        )
        total_debt += cost["total"]

        free_days = cost["free_days"]
        days = cost["days"]
        level, days_left = _classify_warning(days, free_days)

        if level is None:
            continue

        display = c["display_number"]
        company = c["company_name"] or "—"

        if level == "red":
            overdue = abs(days_left)
            warnings["red"].append(
                f"├ {display} ({company}) — {overdue} дн. на тарификации, "
                f"{_format_money(cost['storage'])} $"
            )
        elif level == "yellow":
            warnings["yellow"].append(
                f"├ {display} ({company}) — через {days_left} дн."
            )
        elif level == "green":
            warnings["green"].append(
                f"├ {display} ({company}) — через {days_left} дн."
            )

    _morning_snapshot = {
        "on_terminal": counts.get("on_terminal", 0),
        "total_debt": round(total_debt, 2),
        "timestamp": datetime.now(),
    }

    departed_yesterday = 0
    yesterday = (datetime.now() - timedelta(days=1)).date()
    for c in all_containers:
        if c["status"] != "departed":
            continue
        dep = c["departure_date"]
        if dep:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    if datetime.strptime(dep, fmt).date() == yesterday:
                        departed_yesterday += 1
                    break
                except ValueError:
                    continue

    today_str = datetime.now().strftime("%d.%m.%Y")
    lines = [
        f"📊 <b>Утренний отчёт — {today_str}</b>",
        "",
        f"На терминале: {counts.get('on_terminal', 0)} контейнеров",
        f"В пути: {counts.get('in_transit', 0)} контейнеров",
        f"Вывезено (вчера): {departed_yesterday}",
        "",
        f"💰 Общая сумма к оплате: {_format_money(total_debt)} $",
    ]

    if warnings["red"]:
        lines.append("")
        lines.append("🔴 <b>ТАРИФИКАЦИЯ НАЧАЛАСЬ</b>")
        for w in sorted(warnings["red"]):
            lines.append(w)

    if warnings["yellow"]:
        lines.append("")
        lines.append("🟡 <b>Скоро тарификация (≤ 3 дня)</b>")
        for w in sorted(warnings["yellow"]):
            lines.append(w)

    if warnings["green"]:
        lines.append("")
        lines.append("💚 <b>Приближается тарификация (4–7 дней)</b>")
        for w in sorted(warnings["green"]):
            lines.append(w)

    if not any(warnings.values()):
        lines.append("")
        lines.append("✅ Нет контейнеров, приближающихся к тарификации")

    return "\n".join(lines)


async def build_evening_report() -> str:
    """Формирует текст вечернего итога дня."""
    settings = await get_all_settings()
    counts = await db_cont.count_by_status()
    all_containers = await db_cont.all_containers()

    today = datetime.now().date()
    arrived_today = 0
    departed_today = 0
    revenue_today = 0.0
    current_debt = 0.0

    for c in all_containers:
        reg = c["registered_at"]
        if reg:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    if datetime.strptime(reg, fmt).date() == today:
                        arrived_today += 1
                    break
                except ValueError:
                    continue

        if c["status"] == "departed" and c["departure_date"]:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    if datetime.strptime(c["departure_date"], fmt).date() == today:
                        departed_today += 1
                        cost = calculate_container_cost(
                            c, settings,
                            comp_entry_fee=c["comp_entry_fee"],
                            comp_free_days=c["comp_free_days"],
                            comp_storage_rate=c["comp_storage_rate"],
                            comp_storage_period_days=c["comp_storage_period_days"],
                        )
                        revenue_today += cost["total"]
                    break
                except ValueError:
                    continue

        if c["status"] == "on_terminal":
            cost = calculate_container_cost(
                c, settings,
                comp_entry_fee=c["comp_entry_fee"],
                comp_free_days=c["comp_free_days"],
                comp_storage_rate=c["comp_storage_rate"],
                comp_storage_period_days=c["comp_storage_period_days"],
            )
            current_debt += cost["total"]

    current_on_terminal = counts.get("on_terminal", 0)
    today_str = datetime.now().strftime("%d.%m.%Y")

    lines = [
        f"📋 <b>Итоги дня — {today_str}</b>",
        "",
        f"Прибыло: +{arrived_today} контейнеров",
        f"Вывезено: -{departed_today} контейнеров",
        f"Выручка за вывоз: {_format_money(revenue_today)} $",
    ]

    global _morning_snapshot
    if _morning_snapshot and _morning_snapshot["timestamp"].date() == today:
        prev_count = _morning_snapshot["on_terminal"]
        prev_debt = _morning_snapshot["total_debt"]
        count_diff = current_on_terminal - prev_count
        debt_diff = round(current_debt - prev_debt, 2)

        count_sign = "+" if count_diff >= 0 else ""
        debt_sign = "+" if debt_diff >= 0 else ""

        lines.append("")
        lines.append(
            f"📈 На терминале: {prev_count} → {current_on_terminal} "
            f"({count_sign}{count_diff})"
        )
        lines.append(
            f"💰 Общий долг: {_format_money(prev_debt)} → "
            f"{_format_money(current_debt)} ({debt_sign}{_format_money(debt_diff)}) $"
        )
    else:
        lines.append("")
        lines.append(f"📈 На терминале: {current_on_terminal}")
        lines.append(f"💰 Общий долг: {_format_money(current_debt)} $")

    return "\n".join(lines)
