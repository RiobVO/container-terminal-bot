# Group Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Бот работает в приватных группах Telegram с live-лентой действий, утренними отчётами (06:00) с эскалацией предупреждений, вечерними итогами (20:00) и inline-кнопками.

**Architecture:** Три новых сервиса (group_notify, daily_report, scheduler) + ChatFilterMiddleware для доступа в группы + report_callbacks хендлер для inline-кнопок. Хендлеры register/containers вызывают notify после мутаций. APScheduler управляет расписанием.

**Tech Stack:** aiogram 3.13.1, apscheduler 3.10.4, aiosqlite, Python 3.12+

---

## Структура файлов

| Файл | Действие | Ответственность |
|------|----------|-----------------|
| `config.py` | Modify | +GROUP_IDS, +REPORT_HOUR, +EVENING_REPORT_HOUR, +TIMEZONE |
| `.env.example` | Modify | +новые переменные |
| `requirements.txt` | Modify | +apscheduler |
| `middlewares/chat_filter.py` | Create | Фильтр: private + разрешённые группы |
| `services/group_notify.py` | Create | notify_groups(bot, text, reply_markup?) |
| `services/daily_report.py` | Create | build_morning_report(), build_evening_report() |
| `services/scheduler.py` | Create | init_scheduler(), morning_job(), evening_job() |
| `handlers/report_callbacks.py` | Create | Inline-кнопки под утренним отчётом |
| `bot.py` | Modify | Убрать private-фильтр, подключить ChatFilter, запустить scheduler |
| `handlers/__init__.py` | Modify | +report_callbacks router |
| `handlers/register.py` | Modify | +notify_groups после регистрации |
| `handlers/containers.py` | Modify | +notify_groups после вывоза и удаления |

---

### Task 1: Config + requirements

**Files:**
- Modify: `config.py`
- Modify: `.env.example`
- Modify: `requirements.txt`

- [ ] **Step 1: Обновить config.py — добавить новые поля**

```python
@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str
    admin_ids: frozenset[int]
    group_ids: frozenset[int]
    default_entry_fee: float
    default_free_days: int
    default_storage_rate: float
    default_storage_period_days: int
    report_hour: int
    evening_report_hour: int
    timezone: str
```

В `load_config()` добавить:

```python
raw_group_ids = os.getenv("GROUP_IDS", "")
group_ids = frozenset(int(x) for x in raw_group_ids.split(",") if x.strip())
```

И в return Config(...):
```python
group_ids=group_ids,
report_hour=int(os.getenv("REPORT_HOUR", "6")),
evening_report_hour=int(os.getenv("EVENING_REPORT_HOUR", "20")),
timezone=os.getenv("TIMEZONE", "Asia/Tashkent"),
```

- [ ] **Step 2: Обновить .env.example**

Добавить в конец:
```
GROUP_IDS=
REPORT_HOUR=6
EVENING_REPORT_HOUR=20
TIMEZONE=Asia/Tashkent
```

- [ ] **Step 3: Обновить requirements.txt**

Добавить:
```
apscheduler==3.10.4
```

- [ ] **Step 4: Проверить что config загружается**

```bash
python -c "from config import load_config; c = load_config(); print(f'groups={c.group_ids}, hour={c.report_hour}, tz={c.timezone}')"
```

Expected: `groups=frozenset(), hour=6, tz=Asia/Tashkent`

- [ ] **Step 5: Коммит**

```bash
git add config.py .env.example requirements.txt
git commit -m "feat: add group_ids, report schedule, timezone to config"
```

---

### Task 2: ChatFilterMiddleware

**Files:**
- Create: `middlewares/chat_filter.py`
- Modify: `bot.py:39-41`

- [ ] **Step 1: Создать middlewares/chat_filter.py**

```python
"""Middleware фильтрации чатов: пропускает private + разрешённые группы."""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class ChatFilterMiddleware(BaseMiddleware):
    """Блокирует сообщения из неразрешённых чатов."""

    def __init__(self, group_ids: frozenset[int]) -> None:
        self._group_ids = group_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = None
        if isinstance(event, Message) and event.chat:
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat

        if chat is None:
            return None

        if chat.type == "private":
            return await handler(event, data)

        if chat.type in ("group", "supergroup") and chat.id in self._group_ids:
            return await handler(event, data)

        logger.debug("Чат %s (%s) не в списке разрешённых", chat.id, chat.type)
        return None
```

- [ ] **Step 2: Обновить bot.py — заменить фильтр private на ChatFilterMiddleware**

Убрать строки 39-41:
```python
dp.message.filter(F.chat.type == "private")
dp.callback_query.filter(F.message.chat.type == "private")
```

Добавить импорт и подключение middleware (ПЕРЕД RoleMiddleware):
```python
from middlewares.chat_filter import ChatFilterMiddleware

chat_filter = ChatFilterMiddleware(cfg.group_ids)
dp.message.middleware(chat_filter)
dp.callback_query.middleware(chat_filter)
```

- [ ] **Step 3: Запустить тесты**

```bash
pytest tests/ -v
```

Expected: все 41 тест проходят

- [ ] **Step 4: Коммит**

```bash
git add middlewares/chat_filter.py bot.py
git commit -m "feat: ChatFilterMiddleware — bot works in private + allowed groups"
```

---

### Task 3: services/group_notify.py

**Files:**
- Create: `services/group_notify.py`

- [ ] **Step 1: Создать services/group_notify.py**

```python
"""Отправка уведомлений в разрешённые группы."""
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def notify_groups(
    bot: Bot,
    group_ids: frozenset[int],
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Отправляет сообщение во все разрешённые группы.

    Ошибки отправки (бот удалён, нет прав) логируются,
    но не блокируют основной флоу.
    """
    for gid in group_ids:
        try:
            await bot.send_message(
                chat_id=gid,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except Exception:
            logger.warning("Не удалось отправить в группу %s", gid, exc_info=True)
```

- [ ] **Step 2: Коммит**

```bash
git add services/group_notify.py
git commit -m "feat: group_notify service — sends messages to allowed groups"
```

---

### Task 4: services/daily_report.py

**Files:**
- Create: `services/daily_report.py`
- Test: `tests/test_daily_report.py`

- [ ] **Step 1: Создать tests/test_daily_report.py — тесты для логики предупреждений**

```python
"""Тесты формирования утреннего отчёта и предупреждений."""
import pytest
from datetime import datetime, timedelta

from services.daily_report import _classify_warning, _format_money


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d %H:%M:%S")


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
```

- [ ] **Step 2: Запустить тесты — убедиться что падают**

```bash
pytest tests/test_daily_report.py -v
```

Expected: FAIL (модуль не существует)

- [ ] **Step 3: Создать services/daily_report.py**

```python
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

    # Считаем общую сумму к оплате для активных
    total_debt = 0.0
    warnings: dict[str, list[str]] = {"red": [], "yellow": [], "green": []}

    for c in all_containers:
        if c["status"] not in ("on_terminal",):
            continue

        cost = calculate_container_cost(
            c, settings,
            comp_entry_fee=c["comp_entry_fee"],
            comp_free_days=c["comp_free_days"],
            comp_storage_rate=c["comp_storage_rate"],
            comp_storage_period_days=c["comp_storage_period_days"],
        )
        total_debt += cost["total"]

        # Предупреждения
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

    # Сохраняем снимок для вечернего отчёта
    _morning_snapshot = {
        "on_terminal": counts.get("on_terminal", 0),
        "total_debt": round(total_debt, 2),
        "timestamp": datetime.now(),
    }

    # Вчерашние вывозы
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
        # Прибывшие сегодня
        reg = c["registered_at"]
        if reg:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    if datetime.strptime(reg, fmt).date() == today:
                        arrived_today += 1
                    break
                except ValueError:
                    continue

        # Вывезенные сегодня
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

        # Текущий долг (on_terminal)
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

    # Динамика (если есть утренний снимок)
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
```

- [ ] **Step 4: Запустить тесты**

```bash
pytest tests/test_daily_report.py -v
```

Expected: 5 passed

- [ ] **Step 5: Коммит**

```bash
git add services/daily_report.py tests/test_daily_report.py
git commit -m "feat: daily_report service — morning/evening report builders with warnings"
```

---

### Task 5: services/scheduler.py + inline-кнопки

**Files:**
- Create: `services/scheduler.py`
- Create: `handlers/report_callbacks.py`
- Modify: `handlers/__init__.py`

- [ ] **Step 1: Создать services/scheduler.py**

```python
"""Планировщик автоматических отчётов."""
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.daily_report import build_morning_report, build_evening_report
from services.group_notify import notify_groups

logger = logging.getLogger(__name__)

# ID последнего закреплённого сообщения per group
_pinned_messages: dict[int, int] = {}


def _morning_keyboard() -> InlineKeyboardMarkup:
    """Inline-кнопки под утренним отчётом."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 По компаниям", callback_data="morning:companies"),
            InlineKeyboardButton(text="⚠️ Предупреждения", callback_data="morning:warnings"),
        ],
        [
            InlineKeyboardButton(text="📥 Скачать xlsx", callback_data="morning:xlsx"),
        ],
    ])


async def _send_morning_report(bot: Bot, group_ids: frozenset[int]) -> None:
    """Отправляет утренний отчёт и закрепляет его."""
    text = await build_morning_report()
    kb = _morning_keyboard()

    for gid in group_ids:
        try:
            # Открепляем предыдущий отчёт
            prev_msg_id = _pinned_messages.get(gid)
            if prev_msg_id:
                try:
                    await bot.unpin_chat_message(chat_id=gid, message_id=prev_msg_id)
                except Exception:
                    pass

            msg = await bot.send_message(
                chat_id=gid, text=text, parse_mode="HTML", reply_markup=kb,
            )

            # Закрепляем новый
            try:
                await bot.pin_chat_message(
                    chat_id=gid, message_id=msg.message_id, disable_notification=True,
                )
                _pinned_messages[gid] = msg.message_id
            except Exception:
                logger.warning("Не удалось закрепить отчёт в группе %s", gid)

        except Exception:
            logger.warning("Не удалось отправить утренний отчёт в %s", gid, exc_info=True)


async def _send_evening_report(bot: Bot, group_ids: frozenset[int]) -> None:
    """Отправляет вечерний итог дня."""
    text = await build_evening_report()
    await notify_groups(bot, group_ids, text)


def init_scheduler(
    bot: Bot,
    group_ids: frozenset[int],
    report_hour: int,
    evening_hour: int,
    timezone: str,
) -> AsyncIOScheduler:
    """Создаёт и возвращает настроенный планировщик."""
    scheduler = AsyncIOScheduler(timezone=timezone)

    scheduler.add_job(
        _send_morning_report,
        CronTrigger(hour=report_hour, minute=0),
        args=[bot, group_ids],
        id="morning_report",
        name="Утренний отчёт",
    )

    scheduler.add_job(
        _send_evening_report,
        CronTrigger(hour=evening_hour, minute=0),
        args=[bot, group_ids],
        id="evening_report",
        name="Вечерний итог дня",
    )

    return scheduler
```

- [ ] **Step 2: Создать handlers/report_callbacks.py**

```python
"""Обработчики inline-кнопок под утренним отчётом."""
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile

from db import companies as db_comp
from db import containers as db_cont
from db.settings import get_all_settings
from services.calculator import calculate_container_cost
from services.daily_report import _classify_warning, _format_money
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

    out_dir = Path("/tmp/reports")
    filename = f"report_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

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

    # Удаляем файл после отправки
    try:
        path.unlink()
    except OSError:
        pass
```

- [ ] **Step 3: Обновить handlers/__init__.py — добавить report_callbacks**

Добавить импорт:
```python
from handlers.report_callbacks import router as report_callbacks_router
```

В `setup_routers` перед `fallback_router`:
```python
dp.include_router(report_callbacks_router)
```

- [ ] **Step 4: Запустить тесты**

```bash
pytest tests/ -v
```

Expected: все тесты проходят

- [ ] **Step 5: Коммит**

```bash
git add services/scheduler.py handlers/report_callbacks.py handlers/__init__.py
git commit -m "feat: scheduler + inline report callbacks (companies, warnings, xlsx)"
```

---

### Task 6: Live-лента — notify в хендлерах

**Files:**
- Modify: `handlers/register.py:264-319` (функция `_finalize`)
- Modify: `handlers/containers.py:617-662,824-831` (функции `_finalize_departure`, `delete_confirm`)
- Modify: `bot.py` (передать bot и group_ids в хендлеры)

- [ ] **Step 1: Добавить bot в data — обновить bot.py**

В `bot.py`, после создания `dp`, перед `setup_routers`:
```python
dp["bot_instance"] = bot
dp["group_ids"] = cfg.group_ids
```

- [ ] **Step 2: Обновить handlers/register.py — notify после регистрации**

В конец функции `_finalize` (после отправки карточки, строка ~318), добавить:

```python
    # Live-лента: уведомление в группы
    from services.group_notify import notify_groups
    bot_instance = message.bot
    group_ids = bot_instance.get("group_ids", frozenset())
    # group_ids передан через dp, доступен из data — но проще взять из message.bot
    # Берём из dp через middleware или хак: сохраним в bot при старте
    if hasattr(bot_instance, "_group_ids"):
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        status_text = "На терминале" if status == "on_terminal" else "В пути"
        notify_text = (
            f"📥 <b>Новый контейнер</b>\n"
            f"{display} ({company_name}) — {container_type or 'тип не указан'}\n"
            f"Статус: {status_text}\n"
            f"Оператор: {username}"
        )
        await notify_groups(bot_instance, bot_instance._group_ids, notify_text)
```

Проще: в bot.py после создания bot, добавить `bot._group_ids = cfg.group_ids`.

- [ ] **Step 3: Обновить handlers/containers.py — notify после вывоза**

В функции `_finalize_departure`, после `await message.answer(confirmation)` (строка ~657), добавить:

```python
    if hasattr(message.bot, "_group_ids") and message.bot._group_ids:
        from services.group_notify import notify_groups
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        cost_info = ""
        if mode != "edit":
            settings = await get_all_settings()
            cost = calculate_container_cost(
                fresh, settings,
                comp_entry_fee=fresh["comp_entry_fee"],
                comp_free_days=fresh["comp_free_days"],
                comp_storage_rate=fresh["comp_storage_rate"],
                comp_storage_period_days=fresh["comp_storage_period_days"],
            )
            cost_info = f"Дней на терминале: {cost['days']} | К оплате: {cost['total']} $\n"
        notify_text = (
            f"🚛 <b>Вывоз</b>\n"
            f"{display} ({fresh['company_name'] or '—'})"
            f" — {fresh['type'] or 'тип не указан'}\n"
            f"{cost_info}"
            f"Оператор: {username}"
        )
        await notify_groups(message.bot, message.bot._group_ids, notify_text)
```

- [ ] **Step 4: Обновить handlers/containers.py — notify после удаления**

В функции `delete_confirm`, после `await message.answer("✅ Удалено")` (строка ~830), перед `_show_menu`, добавить:

```python
    if hasattr(message.bot, "_group_ids") and message.bot._group_ids:
        from services.group_notify import notify_groups
        container = await db_cont.get_container(container_id)
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        # container уже удалён, нужно сохранить данные ДО удаления
```

Проблема: контейнер уже удалён к этому моменту. Нужно сохранить display_number ДО удаления. Исправляем: читаем контейнер перед удалением.

Обновлённая `delete_confirm`:
```python
@router.message(ContainerSection.confirming_delete, F.text == BTN_CONFIRM_DELETE)
async def delete_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    container_id = data.get("container_id")
    if container_id is None:
        return

    # Сохраняем данные для уведомления ДО удаления
    container = await db_cont.get_container(container_id)
    display = container["display_number"] if container else "?"
    company = (container["company_name"] or "—") if container else "—"

    await db_cont.delete_container(container_id)
    await message.answer("✅ Удалено")

    if hasattr(message.bot, "_group_ids") and message.bot._group_ids:
        from services.group_notify import notify_groups
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        notify_text = (
            f"🗑 <b>Удалён контейнер</b>\n"
            f"{display} ({company})\n"
            f"Оператор: {username}"
        )
        await notify_groups(message.bot, message.bot._group_ids, notify_text)

    await _show_menu(message, state)
```

- [ ] **Step 5: Обновить bot.py — сохранить group_ids в bot**

После создания `bot` объекта:
```python
bot._group_ids = cfg.group_ids
```

- [ ] **Step 6: Запустить тесты**

```bash
pytest tests/ -v
```

Expected: все тесты проходят

- [ ] **Step 7: Коммит**

```bash
git add bot.py handlers/register.py handlers/containers.py
git commit -m "feat: live feed — notify groups on register, depart, delete"
```

---

### Task 7: Интеграция scheduler в bot.py

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Обновить bot.py — подключить scheduler**

Добавить импорт:
```python
from services.scheduler import init_scheduler
```

В функции `main()`, после `setup_routers(dp)` и перед `bot.set_my_commands`:

```python
    # Планировщик отчётов (только если есть группы)
    if cfg.group_ids:
        scheduler = init_scheduler(
            bot=bot,
            group_ids=cfg.group_ids,
            report_hour=cfg.report_hour,
            evening_hour=cfg.evening_report_hour,
            timezone=cfg.timezone,
        )
        scheduler.start()
        logger.info(
            "Планировщик запущен: утренний=%02d:00, вечерний=%02d:00, tz=%s",
            cfg.report_hour, cfg.evening_report_hour, cfg.timezone,
        )
```

- [ ] **Step 2: Установить зависимости и проверить импорты**

```bash
pip install apscheduler==3.10.4
python -c "from services.scheduler import init_scheduler; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Запустить все тесты**

```bash
pytest tests/ -v
```

Expected: все тесты проходят

- [ ] **Step 4: Коммит**

```bash
git add bot.py
git commit -m "feat: integrate APScheduler — morning and evening reports on cron"
```

---

### Task 8: Тесты интеграции

**Files:**
- Create: `tests/test_group_notify.py`
- Create: `tests/test_chat_filter.py`

- [ ] **Step 1: Создать tests/test_chat_filter.py**

```python
"""Тесты ChatFilterMiddleware."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from middlewares.chat_filter import ChatFilterMiddleware


@pytest.fixture
def middleware():
    return ChatFilterMiddleware(group_ids=frozenset({-100123}))


def _make_message(chat_type: str, chat_id: int = 0) -> MagicMock:
    msg = MagicMock()
    msg.chat.type = chat_type
    msg.chat.id = chat_id
    return msg


async def test_private_allowed(middleware):
    """Private-чат всегда пропускается."""
    handler = AsyncMock()
    event = _make_message("private")
    await middleware(handler, event, {})
    handler.assert_called_once()


async def test_allowed_group(middleware):
    """Разрешённая группа пропускается."""
    handler = AsyncMock()
    event = _make_message("supergroup", chat_id=-100123)
    await middleware(handler, event, {})
    handler.assert_called_once()


async def test_unknown_group_blocked(middleware):
    """Неразрешённая группа блокируется."""
    handler = AsyncMock()
    event = _make_message("supergroup", chat_id=-100999)
    await middleware(handler, event, {})
    handler.assert_not_called()


async def test_channel_blocked(middleware):
    """Канал блокируется."""
    handler = AsyncMock()
    event = _make_message("channel", chat_id=-100555)
    await middleware(handler, event, {})
    handler.assert_not_called()
```

- [ ] **Step 2: Создать tests/test_group_notify.py**

```python
"""Тесты services.group_notify."""
import pytest
from unittest.mock import AsyncMock, patch

from services.group_notify import notify_groups


async def test_notify_sends_to_all_groups():
    """Сообщение отправляется во все группы."""
    bot = AsyncMock()
    await notify_groups(bot, frozenset({-1, -2}), "test")
    assert bot.send_message.call_count == 2


async def test_notify_error_does_not_raise():
    """Ошибка в одной группе не ломает отправку в другие."""
    bot = AsyncMock()
    bot.send_message.side_effect = [Exception("fail"), None]
    await notify_groups(bot, frozenset({-1, -2}), "test")
    assert bot.send_message.call_count == 2


async def test_notify_empty_groups():
    """Пустой список групп — ничего не отправляется."""
    bot = AsyncMock()
    await notify_groups(bot, frozenset(), "test")
    bot.send_message.assert_not_called()
```

- [ ] **Step 3: Запустить все тесты**

```bash
pytest tests/ -v
```

Expected: все тесты проходят

- [ ] **Step 4: Коммит**

```bash
git add tests/test_chat_filter.py tests/test_group_notify.py
git commit -m "test: add ChatFilterMiddleware and group_notify tests"
```

---

## Сводка по задачам

| Task | Описание | Файлы | Тесты |
|------|----------|-------|-------|
| 1 | Config + requirements | config.py, .env.example, requirements.txt | — |
| 2 | ChatFilterMiddleware | middlewares/chat_filter.py, bot.py | test_chat_filter.py |
| 3 | group_notify service | services/group_notify.py | test_group_notify.py |
| 4 | daily_report service | services/daily_report.py | test_daily_report.py |
| 5 | Scheduler + inline callbacks | services/scheduler.py, handlers/report_callbacks.py | — |
| 6 | Live-лента в хендлерах | handlers/register.py, handlers/containers.py, bot.py | — |
| 7 | Интеграция scheduler в bot.py | bot.py | — |
| 8 | Тесты интеграции | — | test_chat_filter.py, test_group_notify.py |
