# Бот учёта контейнеров

Telegram-бот для учёта контейнеров на терминале. Aiogram 3.x, SQLite (aiosqlite), отчёты xlsx (openpyxl).

## Быстрый старт

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

Скопируй `.env.example` → `.env` и заполни:

```
BOT_TOKEN=<токен от @BotFather>
ADMIN_IDS=<tg_id администратора(ов), через запятую>
DB_PATH=container.db        # путь к файлу БД (опционально)
```

Запуск:

```bash
python bot.py
```

## Роли

| Роль | Доступ |
|------|--------|
| admin | Все разделы, включая «🏢 Компании» |
| operator | «📦 Контейнер», «🚚 Вывоз», «📊 Отчёт» |

Роль задаётся при первом `/start`: если `tg_id` пользователя есть в `ADMIN_IDS` — admin, иначе operator.

## Первые шаги

1. Написать боту `/start`.
2. Администратор: нажать «🏢 Компании» → «➕ Добавить компанию», ввести параметры тарифа.
3. Оператор: «📦 Контейнер» → ввести номер, выбрать компанию, тип, дату прибытия.
4. При вывозе: «🚚 Вывоз» → номер → дата → бот покажет сумму.
5. «📊 Отчёт» → компания → месяц → вид → получить xlsx.

## Формат номера контейнера

ISO 6346: 4 заглавные латинские буквы + 7 цифр. Пример: `TEMU 6275401` или `TEMU6275401`.

## Формула расчёта задолженности

```
days_stored = (дата вывоза или сегодня) - дата прибытия
billable    = max(0, days_stored - free_days)
storage     = (billable / storage_period_days) * storage_rate
total       = entry_fee + storage
```

## Имя файла отчёта

`report_<Компания>_<all|departed>_<YYYY-MM-DD_HH-MM-SS>.xlsx`
