# CLAUDE.md

Гайд для Claude Code при работе в этом репо.

## Что это

Telegram-бот учёта контейнеров на терминале. aiogram 3.x, SQLite (aiosqlite), Redis (FSM), APScheduler, отчёты xlsx (openpyxl). Python 3.12+. Разворачивается через Docker Compose.

## Команды

### Локально (разработка)

```bash
.venv/Scripts/activate        # Windows
source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
python bot.py
python -m tests.test_calculator   # свой раннер, не pytest
```

### Прод (DigitalOcean, 188.166.127.192)

```bash
ssh deploy@188.166.127.192
cd ~/container
git pull
docker compose up -d --build
docker compose logs -f bot
```

Другие полезные:
```bash
docker compose ps              # что запущено
docker compose restart bot     # перезапуск только бота
docker compose down            # стоп всё (данные целы в data/ и redis-data volume)
```

## Переменные окружения (.env)

Обязательные: `BOT_TOKEN`.
Полезные: `ADMIN_IDS` (через запятую), `GROUP_IDS` (куда идут отчёты), `BACKUP_CHAT_ID` (канал бэкапов БД).
С дефолтами: `DEFAULT_ENTRY_FEE=20`, `DEFAULT_FREE_DAYS=30`, `DEFAULT_STORAGE_RATE=20`, `DEFAULT_STORAGE_PERIOD_DAYS=30`, `REPORT_HOUR=6`, `EVENING_REPORT_HOUR=20`, `TIMEZONE=Asia/Tashkent`.

В проде `REDIS_URL` и `DATABASE_PATH` задаёт docker-compose (`redis://redis:6379/0` и `/app/data/container.db`), в `.env` их не пишем.

Конфиг загружается `config.py:load_config()`. Фолбэк `DATABASE_PATH → DB_PATH → "bot.db"`.

## Архитектура

### БД (`db/`)

Актуальный пакет: `schema.py` (DDL v2), `migrations.py` (v0→v1→v2→operator role), `users.py`, `companies.py`, `containers.py`, `settings.py`. Подключение через `db.get_db()`.

Легаси `db.py` в корне не используется — **не трогать, все изменения в `db/`**.

Схема v2 — 4 таблицы: `global_settings` (key/value), `companies` (4 параметра тарифа, каждый NULL = стандарт), `containers` (status: in_transit / on_terminal / departed), `users` (роли: full / operator / reports_only / none).

Миграции запускаются автоматически из `init_db`, делают бэкап `.backup_YYYYMMDD_HHMMSS` рядом с БД **до** изменений. Идемпотентны — проверяют фактическое состояние схемы.

### Тарификация (`services/calculator.py`)

Центральная логика. Per-company параметры с фолбэком на `global_settings`. Периоды считаются через `math.ceil` (неполный период = полный). Тесты в `tests/test_calculator.py`.

### Номера контейнеров

ISO 6346: 4 буквы + 7 цифр. Нормализация в `services/normalizer.py`. В БД хранятся `number` (без пробелов, upper) и `display_number` (с пробелом: `TEMU 6275401`).

### Роутеры и FSM

- `handlers/__init__.py` → `setup_routers(dp)` регистрирует все роутеры, `fallback_router` — последний
- FSM-состояния: `states.py` (по StatesGroup на поток)
- Клавиатуры: `keyboards/` (reply-first, по модулю на раздел)
- Middleware: `chat_filter.py` (ограничение по private + разрешённые группы), `role.py` (кладёт роль в `data["role"]`)
- FSM-стор: Redis в проде, MemoryStorage локально (ленивая инициализация в `bot.py:45-54`, автофолбэк при недоступном Redis)
- Утренний снимок для вечернего diff персистится в `data/morning_snapshot.json` — переживает рестарт

### Отчёты

- `services/report_generator.py` — актуальный генератор xlsx, разбивка по листам-месяцам, use `services/calculator.py`
- `services/daily_report.py` — текстовые утренний (06:00, с предупреждениями о приближении тарификации и пином сообщения) и вечерний (20:00, итоги дня с diff от утра) отчёты
- `services/scheduler.py` — APScheduler: утро, вечер, бэкап БД каждые 6ч (03/09/15/21:00 по TIMEZONE)
- `reports.py` в корне — legacy, **не трогать**

### Автобэкапы БД

Файл копируется в `data/backups/` с ротацией >7 дней + отправляется как документ в `BACKUP_CHAT_ID` (Telegram-канал). Ручной бэкап — команда `/backup` (только `full`).

## Прод-инфраструктура

- **Сервер**: DigitalOcean droplet 1GB/25GB, Ubuntu 24.04, `188.166.127.192`, юзер `deploy`
- **Репо**: https://github.com/RiobVO/container-terminal-bot
- **Путь на сервере**: `~/container/`
- **Docker Compose**: два контейнера — `container-bot` и `container-redis`
- **БД**: bind-mount `./data/container.db` (владелец UID 1000 = appuser в контейнере)
- **Redis**: named volume `redis-data`, AOF persistence (`--appendonly yes --appendfsync everysec`)
- **Таймзона**: `ENV TZ=Asia/Tashkent` в Dockerfile (иначе `datetime.now()` в UTC)
- **Лог-ротация**: Docker json-file, 10MB × 3 файла

### Перенос БД на сервер (если нужно)

```bash
# Локально: остановить бота (Ctrl+C), убедиться что нет container.db-wal/shm
scp container.db deploy@188.166.127.192:~/container/data/container.db
# На сервере:
sudo chown 1000:1000 ~/container/data/container.db
docker compose restart bot
```

## Критические правила

### Деплой и окружение

- **Один токен = один инстанс.** Telegram polling работает только у одного. Локально не запускать пока работает прод (или завести отдельного тест-бота).
- **`.env` никогда в git.** Уже в `.gitignore`, не трогать.
- **SQLite копировать только на остановленном боте.** Иначе WAL не зафлашен.
- **`docker compose down -v` удаляет вольюмы** (Redis AOF). Использовать только осознанно.

### Код

- **YAGNI**: не добавлять абстракции/фолбэки/валидации для того чего не попросили
- **Scope**: перед изменением ≥2 файлов — объявить «Меняю: X, Y. Не трогаю: Z»
- **Логи**: только `logging`, не `print`
- **Комментарии**: объясняют *почему*, не *что*. Язык — русский. Без трейл-саммари в ответах.
- **Верификация**: после задачи — одна конкретная команда с детерминированным pass/fail. Не «должно работать».
- **Не рефакторить попутно.** Только то что просили.

### Язык

- Общение, комментарии, docstrings — **русский**
- Идентификаторы, коммиты, env-ключи — **английский**

## Известные шероховатости (не блокеры)

- SQLite без WAL mode — ок при одном процессе и ~10 юзеров, не менять без нужды
- `_cfg = load_config()` на import-time в `handlers/start.py` и `handlers/settings.py` — работает в докере (env vars от compose), может сломать тесты без `.env`
- `message.bot._group_ids` — приватный атрибут, монкей-патч в `bot.py:41`. Работает, при обновлении aiogram может потребовать правки.
