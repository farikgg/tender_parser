import asyncpg

from datetime import datetime

from app.core.enums import ParseRunStatus
from app.core.exceptions import RepositoryError


MAX_ERROR_LENGTH = 4000

class ParseRunRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create(self, source_id: int) -> int:
        """Создать запись о начале запуска парсинга. Возвращает id записи."""
        try:
            parse_run_id: int = await self.pool.fetchval(
                """
                INSERT INTO tender_parser.parse_runs (source_id, status)
                VALUES ($1, $2)
                RETURNING id
                """,
                source_id,
                ParseRunStatus.RUNNING,
            )
        except (asyncpg.PostgresError, OSError) as error:
            raise RepositoryError(
                f"Ошибка БД при создании parse_run для source_id={source_id}"
            ) from error

        if parse_run_id is None:
            raise RepositoryError(
                f"Не удалось создать parse_run для source_id={source_id}: RETURNING вернул None"
            )

        return parse_run_id

    async def get_last_success_started_at(self, source_id: int) -> datetime | None:
        """Получить последний 'успешный' запуск парсера"""
        try:
            last_success_started_at = await self.pool.fetchval(
                """
                SELECT started_at FROM tender_parser.parse_runs
                WHERE source_id = $1 AND status = $2 
                ORDER BY started_at DESC
                LIMIT 1
                """,
                source_id,
                ParseRunStatus.SUCCESS,
            )
        except (asyncpg.PostgresError, OSError) as error:
            raise RepositoryError(
                f"Ошибка БД при получении last success для source_id={source_id}"
            ) from error

        return last_success_started_at

    async def mark_success(self, run_id: int, tenders_found: int, tenders_saved: int) -> None:
        """Изменить статус запуска парсера на 'успешный'"""
        try:
            await self.pool.execute(
                """
                UPDATE tender_parser.parse_runs SET
                    status = $1,
                    finished_at = NOW(),
                    tenders_found = $2,
                    tenders_saved = $3
                WHERE id = $4
                """,
                ParseRunStatus.SUCCESS,
                tenders_found,
                tenders_saved,
                run_id
            )
        except (asyncpg.PostgresError, OSError) as error:
            raise RepositoryError(
                f"Ошибка БД. Не удалось обновить status: {ParseRunStatus.SUCCESS} у run_id: {run_id}"
            ) from error

    async def mark_failure(self, run_id: int, error_message: str) -> None:
        """Изменить статус запуска парсера на 'провал'"""
        try:
            await self.pool.execute(
                """
                UPDATE tender_parser.parse_runs SET
                    status = $1,
                    finished_at = NOW(),
                    error_message = $2
                WHERE id = $3
                """,
                ParseRunStatus.FAILED,
                error_message[:MAX_ERROR_LENGTH],
                run_id
            )
        except (asyncpg.PostgresError, OSError) as error:
            raise RepositoryError(
                f"Ошибка БД. Не удалось обновить status: {ParseRunStatus.FAILED} у run_id: {run_id}"
            ) from error

    async def mark_partial(
            self,
            run_id: int,
            tenders_found: int,
            tenders_saved: int,
            error_message: str,
    ) -> None:
        """Изменить статус запуска парсера на 'неполноценный'"""
        try:
            await self.pool.execute(
                """
                UPDATE tender_parser.parse_runs SET
                    status = $1,
                    finished_at = NOW(),
                    tenders_found = $2,
                    tenders_saved = $3,
                    error_message = $4
                WHERE id = $5
                """,
                ParseRunStatus.PARTIAL,
                tenders_found,
                tenders_saved,
                error_message[:MAX_ERROR_LENGTH],
                run_id
            )
        except (asyncpg.PostgresError, OSError) as error:
            raise RepositoryError(
                f"Ошибка БД. Не удалось обновить status: {ParseRunStatus.PARTIAL} у run_id: {run_id}"
            ) from error
