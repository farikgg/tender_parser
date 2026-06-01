import asyncpg
import logging

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
_CREATE_SCHEMA = f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}";'


# Источники парсинга (справочник)
_CREATE_SOURCES = f"""
CREATE TABLE IF NOT EXISTS "{settings.db_schema}".sources (
    id          SMALLSERIAL PRIMARY KEY,
    code        VARCHAR(50)  NOT NULL UNIQUE,
    name        VARCHAR(255) NOT NULL,
    base_url    VARCHAR(500) NOT NULL,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
"""


# Тендеры
_CREATE_TENDERS = f"""
CREATE TABLE IF NOT EXISTS "{settings.db_schema}".tenders (
    id                BIGSERIAL    PRIMARY KEY,
    source_id         SMALLINT     NOT NULL REFERENCES "{settings.db_schema}".sources(id),
    external_id       VARCHAR(255) NOT NULL,
    title             TEXT         NOT NULL,
    description       TEXT,
    url               TEXT NOT NULL,
    customer_name     VARCHAR(1000),
    customer_bin      VARCHAR(30),
    amount            NUMERIC(18, 2),
    currency          CHAR(3)      NOT NULL DEFAULT 'KZT',
    published_at      TIMESTAMPTZ,
    deadline_at       TIMESTAMPTZ,
    status            VARCHAR(20)  NOT NULL DEFAULT 'unknown',
    is_insurance      BOOLEAN      NOT NULL DEFAULT FALSE,
    matched_keywords  TEXT[]       NOT NULL DEFAULT '{{}}',
    raw_data          JSONB        NOT NULL DEFAULT '{{}}'::jsonb,
    first_seen_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenders_source_external UNIQUE (source_id, external_id)
);
"""


_CREATE_TENDERS_INDEXES = [
    f"""CREATE INDEX IF NOT EXISTS idx_tenders_published_at
        ON "{settings.db_schema}".tenders (published_at DESC NULLS LAST);""",
    f"""CREATE INDEX IF NOT EXISTS idx_tenders_is_insurance
        ON "{settings.db_schema}".tenders (is_insurance)
        WHERE is_insurance = TRUE;""",
    f"""CREATE INDEX IF NOT EXISTS idx_tenders_source_published
        ON "{settings.db_schema}".tenders (source_id, published_at DESC NULLS LAST);""",
    f"""CREATE INDEX IF NOT EXISTS idx_tenders_deadline_at
        ON "{settings.db_schema}".tenders (deadline_at)
        WHERE deadline_at IS NOT NULL;""",
]


# История запусков парсинга
_CREATE_PARSE_RUNS = f"""
CREATE TABLE IF NOT EXISTS "{settings.db_schema}".parse_runs (
    id              BIGSERIAL    PRIMARY KEY,
    source_id       SMALLINT     NOT NULL REFERENCES "{settings.db_schema}".sources(id),
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20)  NOT NULL,
    tenders_found   INTEGER      NOT NULL DEFAULT 0,
    tenders_saved   INTEGER      NOT NULL DEFAULT 0,
    error_message   TEXT
);
"""


_CREATE_PARSE_RUNS_INDEXES = [
    f"""CREATE INDEX IF NOT EXISTS idx_parse_runs_source_started
        ON "{settings.db_schema}".parse_runs (source_id, started_at DESC);""",
    f"""CREATE INDEX IF NOT EXISTS idx_parse_runs_status
        ON "{settings.db_schema}".parse_runs (status)
        WHERE status IN ('running', 'failed');""",
]


# Сидинг справочника источников
_SEED_SOURCES = f"""
INSERT INTO "{settings.db_schema}".sources (code, name, base_url) VALUES
    ('goszakup',     'Государственные закупки РК',     'https://v3bl.goszakup.gov.kz/'),
    ('mp_kz',        'Marketplace mp.kz',              'https://mp.kz/'),
    ('mitwork',      'Евразийский электронный портал', 'https://eep.mitwork.kz/'),
    ('eurasiantech', 'EurasianTech Tender',            'https://eurasiantech-tender.kz/')
ON CONFLICT (code) DO NOTHING;
"""


async def init_schema(pool: asyncpg.Pool) -> None:
    """
    Инициализировать схему БД.

    Идемпотентная операция — можно вызывать при каждом старте приложения.
    Все таблицы и индексы создаются с IF NOT EXISTS.

    Args:
        pool: Пул соединений asyncpg.

    Raises:
        asyncpg.PostgresError: При ошибке выполнения DDL.
    """
    logger.info("Инициализация схемы БД '%s'...", settings.db_schema)

    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(_CREATE_SCHEMA)
        await conn.execute(_CREATE_SOURCES)
        await conn.execute(_CREATE_TENDERS)

        for index_sql in _CREATE_TENDERS_INDEXES:
            await conn.execute(index_sql)
        await conn.execute(_CREATE_PARSE_RUNS)

        for index_sql in _CREATE_PARSE_RUNS_INDEXES:
            await conn.execute(index_sql)
        await conn.execute(_SEED_SOURCES)

    logger.info("Схема БД инициализирована")
