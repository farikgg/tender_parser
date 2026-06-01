# garant-tender-parser

Парсер тендеров по страхованию с закупочных площадок РК.

## Назначение

Сервис автоматически собирает информацию о тендерах с закупочных площадок,
классифицирует их по наличию ключевых слов, связанных со страхованием,
и сохраняет в собственную БД. На запросы из других сервисов компании не отвечает —
данные предоставляются через прямой доступ к БД.

## Источники

| Код | Площадка | Способ доступа |
|---|---|---|
| `goszakup` | goszakup.gov.kz | GraphQL API |
| `mp_kz` | mp.kz | HTML-парсинг |
| `mitwork` | eep.mitwork.kz | HTML-парсинг |
| `eurasiantech` | eurasiantech-tender.kz | HTML-парсинг |

## Стек

- Python 3.13
- httpx (async HTTP)
- BeautifulSoup + lxml (HTML)
- asyncpg (PostgreSQL, raw SQL)
- pydantic v2 + pydantic-settings
- APScheduler 3.x
- pytest + pytest-asyncio
- ruff + mypy (strict)

## Архитектура

```
APScheduler
    ↓
ParserService (оркестратор)
    ↓
BaseSource (4 реализации)  →  ClassifierService  →  TenderRepository  →  PostgreSQL
```

Подробнее — см. `docs/architecture.md` (будет добавлен позже).

## Запуск локально

1. Создать `.env` из `.env.example` и заполнить значения
2. Поднять PostgreSQL (можно через `docker-compose up -d` — будет добавлен на Этапе 2)
3. Установить зависимости:

   ```bash
   pip install -e ".[dev]"
   ```

4. Запустить приложение:

   ```bash
   python -m src.main
   ```

   Схема БД создастся автоматически при первом запуске.

## Расписание

Парсер запускается **каждый час с 09:00 до 17:00, с понедельника по пятницу**,
по времени `Asia/Almaty`. Настраивается через переменные окружения
`SCHEDULER_CRON_*`.

## Разработка

```bash
# Линтер
ruff check src tests
ruff format src tests

# Типы
mypy src

# Тесты
pytest
```

## Git-соглашения

См. корпоративные соглашения по веткам и коммитам.
Формат веток: `{type}/{TASK-ID}/{short-description}` (например, `feat/TPR-1/initial-setup`).