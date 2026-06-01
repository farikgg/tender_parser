import asyncpg
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


async def create_pool() -> asyncpg.Pool:
    """Создаёт и возвращает пул соединений asyncpg."""
    settings = get_settings()

    try:
        pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=settings.db_command_timeout,
            max_inactive_connection_lifetime=settings.db_inactive_lifetime,
            server_settings={"application_name": "garant-tender-parser"},
        )
    except Exception:
        logger.exception("Не удалось создать пул соединений к БД")
        raise

    logger.info("Пул соединений создан")
    return pool

async def close_pool(pool: asyncpg.Pool) -> None:
    """Корректно закрыть пул соединений."""
    await pool.close()
    logger.info("Пул соединений закрыт")
