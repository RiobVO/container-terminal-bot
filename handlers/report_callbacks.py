"""Обработчики inline-кнопок: утренний отчёт в канале + команда /report."""
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile

from db import containers as db_cont
from db.settings import get_all_settings
from services.calculator import calculate_container_cost
from services.daily_report import (
    _classify_warning, _format_money, build_morning_report, build_evening_report,
)
from services.group_notify import notify_groups
from services.report_generator import build_report

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "morning:companies")
async def morning_companies(callback: CallbackQuery) -> None:
    """Разбивка по компаниям: количество и сумма."""
    settings = await get_all_settings()
    all_containers = await db_cont.all_containers()

    company_stats: dict[str, dict] = {}
    for c in all_containers:
        if c["status"] != "on_terminal":
            continue
        name = c["company_name"] or "—"
        cost = calculate_container_cost(
            c, settings,
            comp_entry_fee=c["comp_entry_fee"],
            comp_free_days=c["comp_free_days"],
            comp_storage_rate=c["comp_storage_rate"],
            comp_storage_period_days=c["comp_storage_period_days"],
        )
        if name not in company_stats:
            company_stats[name] = {"count": 0, "total": 0.0}
        company_stats[name]["count"] += 1
        company_stats[name]["total"] += cost["total"]

    if not company_stats:
        await callback.answer("Нет контейнеров на терминале", show_alert=True)
        return

    lines = ["📦 <b>По компаниям (на терминале)</b>", ""]
    for name in sorted(company_stats.keys(), key=str.lower):
        s = company_stats[name]
        lines.append(f"🏢 {name}: {s['count']} шт — {_format_money(s['total'])} $")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "morning:warnings")
async def morning_warnings(callback: CallbackQuery) -> None:
    """Полный список предупреждений по тарификации."""
    settings = await get_all_settings()
    all_containers = await db_cont.all_containers()

    warnings: list[tuple[int, str]] = []
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
        level, days_left = _classify_warning(cost["days"], cost["free_days"])
        if level is None:
            continue
        display = c["display_number"]
        company = c["company_name"] or "—"
        icon = {"red": "🔴", "yellow": "🟡", "green": "💚"}[level]
        if level == "red":
            text = f"{icon} {display} ({company}) — {abs(days_left)} дн. на тарификации"
        else:
            text = f"{icon} {display} ({company}) — через {days_left} дн."
        warnings.append((days_left, text))

    if not warnings:
        await callback.answer("Нет предупреждений", show_alert=True)
        return

    warnings.sort(key=lambda x: x[0])
    lines = ["⚠️ <b>Все предупреждения</b>", ""]
    lines.extend(w[1] for w in warnings)

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "morning:xlsx")
async def morning_xlsx(callback: CallbackQuery) -> None:
    """Генерирует и отправляет xlsx-отчёт."""
    settings = await get_all_settings()
    containers = await db_cont.fetch_for_report(("on_terminal", "departed"))

    if not containers:
        await callback.answer("Нет данных для отчёта", show_alert=True)
        return

    out_dir = Path(tempfile.gettempdir()) / "reports"
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    path = build_report(
        containers, settings, out_dir, filename,
        group_field="arrival_date",
        summary_sheet_name="Сводка",
    )

    await callback.message.answer_document(
        FSInputFile(path, filename=filename),
        caption="📊 Отчёт по всем контейнерам",
    )
    await callback.answer()

    try:
        path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Кнопки команды /report (из личного чата админа → в канал)
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "cmd_report:morning")
async def cmd_report_morning(callback: CallbackQuery) -> None:
    """Отправляет утренний отчёт в канал."""
    group_ids = getattr(callback.bot, "_group_ids", frozenset())
    if not group_ids:
        await callback.answer("GROUP_IDS не настроены", show_alert=True)
        return

    from services.scheduler import _morning_keyboard
    text = await build_morning_report()
    await notify_groups(callback.bot, group_ids, text, reply_markup=_morning_keyboard())
    await callback.answer("✅ Утренний отчёт отправлен в канал", show_alert=True)


@router.callback_query(F.data == "cmd_report:evening")
async def cmd_report_evening(callback: CallbackQuery) -> None:
    """Отправляет вечерний итог дня в канал."""
    group_ids = getattr(callback.bot, "_group_ids", frozenset())
    if not group_ids:
        await callback.answer("GROUP_IDS не настроены", show_alert=True)
        return

    text = await build_evening_report()
    await notify_groups(callback.bot, group_ids, text)
    await callback.answer("✅ Итоги дня отправлены в канал", show_alert=True)


@router.callback_query(F.data == "cmd_report:xlsx")
async def cmd_report_xlsx(callback: CallbackQuery) -> None:
    """Генерирует xlsx и отправляет в канал."""
    group_ids = getattr(callback.bot, "_group_ids", frozenset())
    if not group_ids:
        await callback.answer("GROUP_IDS не настроены", show_alert=True)
        return

    settings = await get_all_settings()
    containers = await db_cont.fetch_for_report(("on_terminal", "departed"))

    if not containers:
        await callback.answer("Нет данных для отчёта", show_alert=True)
        return

    out_dir = Path(tempfile.gettempdir()) / "reports"
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    path = build_report(
        containers, settings, out_dir, filename,
        group_field="arrival_date", summary_sheet_name="Сводка",
    )

    for gid in group_ids:
        try:
            await callback.bot.send_document(
                chat_id=gid,
                document=FSInputFile(path, filename=filename),
                caption="📊 Отчёт по всем контейнерам",
            )
        except Exception:
            logger.warning("Не удалось отправить xlsx в %s", gid)

    await callback.answer("✅ xlsx отправлен в канал", show_alert=True)

    try:
        path.unlink()
    except OSError:
        pass
