# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

Telegram-бот учёта контейнеров на терминале. Aiogram 3.x, SQLite (aiosqlite), отчёты xlsx (openpyxl). Python 3.12+.

## Команды

```bash
# Активация окружения
.venv/Scripts/activate        # Windows
source .venv/bin/activate     # Linux/macOS

# Установка зависимостей
pip install -r requirements.txt

# Запуск бота
python bot.py

# Тесты калькулятора (pytest не используется — собственный раннер)
python -m tests.test_calculator
```

## Переменные окружения (.env)

`BOT_TOKEN`, `ADMIN_IDS` (через запятую), `DATABASE_PATH` (по умолчанию `bot.db`), `DEFAULT_ENTRY_FEE`, `DEFAULT_FREE_DAYS`, `DEFAULT_STORAGE_RATE`, `DEFAULT_STORAGE_PERIOD_DAYS`.

## Архитектура

### Два слоя БД

Проект содержит **два** модуля доступа к данным:
- `db.py` — устаревший (legacy), использовался ранней версией. Содержит свой DDL и функции. **Не используется активным кодом.**
- `db/` — актуальный пакет: `schema.py` (DDL v2), `migrations.py` (v0→v1→v2), `users.py`, `companies.py`, `containers.py`, `settings.py`. Подключение через `db.get_db()`.

Все новые изменения — только в `db/`.

### Схема БД (v2)

Четыре таблицы: `global_settings` (key/value), `companies` (гибкий тариф: entry_fee, free_days, storage_rate, storage_period_days — NULL = стандартное из global_settings), `containers` (статус: in_transit / on_terminal / departed), `users` (роли: full / reports_only / none).

Миграции (`db/migrations.py`) запускаются автоматически при `init_db` и делают бэкап перед изменениями.

### Модель тарификации

`services/calculator.py` — центральная логика расчёта. Периоды считаются через `math.ceil` (неполный период = полный). Per-company параметры с фолбэком на global_settings. Тесты в `tests/test_calculator.py`.

### Роутеры и FSM

- `handlers/__init__.py` → `setup_routers(dp)` регистрирует все роутеры. `fallback_router` — последний.
- FSM-состояния: `states.py` — StatesGroup для каждого потока (контейнеры, компании, отчёты, настройки).
- Клавиатуры: `keyboards/` — по модулю на раздел.
- `middlewares/role.py` — RoleMiddleware кладёт роль в `data["role"]`.

### Отчёты

`reports.py` — legacy-генератор xlsx (использует `utils.calculate_total`).
`services/report_generator.py` — актуальный генератор (использует `services/calculator.py`).

### Номера контейнеров

ISO 6346: 4 буквы + 7 цифр. Нормализация в `services/normalizer.py`. В БД хранятся `number` (без пробелов, upper) и `display_number` (с пробелом: `TEMU 6275401`).
