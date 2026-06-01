import asyncpg
import json
import logging

from app.core.enums import SourceCode
from app.core.exceptions import RepositoryError
from app.core.models import ClassifiedTender

logger = logging.getLogger(__name__)


class TenderRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_source_id_by_code(self, code: SourceCode) -> int:
        """Получить id из таблицы sources по коду. Бросает RepositoryError если не найден."""
        try:
            source_id = await self.pool.fetchval(
                "SELECT id FROM tender_parser.sources WHERE code = $1",
                code,
            )
        except (asyncpg.PostgresError, OSError) as error:
            raise RepositoryError(
                f"Ошибка БД при получении source_id для code={code}"
            ) from error

        if source_id is None:
            raise RepositoryError(f"Source с code={code} не найден в БД")

        return source_id

    async def upsert(self, classified: ClassifiedTender, source_id: int) -> None:
        """Вставить или обновить тендер. ON CONFLICT (source_id, external_id) DO UPDATE."""
        query = """
        INSERT INTO tender_parser.tenders (
            source_id,
            external_id, 
            title, 
            description, 
            url, 
            customer_name, 
            customer_bin, 
            amount, 
            currency, 
            published_at, 
            deadline_at, 
            status, 
            is_insurance, 
            matched_keywords, 
            raw_data
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9,
            $10, $11, $12, $13, $14, $15::jsonb
        )
        ON CONFLICT (source_id, external_id) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            url = EXCLUDED.url,
            customer_name = EXCLUDED.customer_name,
            customer_bin = EXCLUDED.customer_bin,
            amount = EXCLUDED.amount,
            currency = EXCLUDED.currency,
            published_at = EXCLUDED.published_at,
            deadline_at = EXCLUDED.deadline_at,
            status = EXCLUDED.status,
            is_insurance = EXCLUDED.is_insurance,
            matched_keywords = EXCLUDED.matched_keywords,
            raw_data = EXCLUDED.raw_data,          
            last_seen_at = NOW(),
            updated_at = NOW()
        """

        try:
            await self.pool.execute(
                query,
                source_id,
                classified.raw.external_id,
                classified.raw.title,
                classified.raw.description,
                str(classified.raw.url),
                classified.raw.customer_name,
                classified.raw.customer_bin,
                classified.raw.amount,
                classified.raw.currency,
                classified.raw.published_at,
                classified.raw.deadline_at,
                classified.raw.status,
                classified.is_insurance,
                classified.matched_keywords,
                json.dumps(classified.raw.raw_data)
            )
        except (asyncpg.PostgresError, OSError) as error:
            logger.exception("Ошибка БД при upsert тендера %s", classified.raw.external_id)
            raise RepositoryError(
                f"Ошибка БД при обновлении тендера: {classified.raw.title}"
            ) from error
