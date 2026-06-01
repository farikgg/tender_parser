import asyncio
import logging

import httpx

from app.core.enums import SourceCode
from app.core.exceptions import (
    ConfigurationError,
    RepositoryError,
    SourceError,
)
from app.core.models import ParseSourceResult
from app.repository.parse_run_repository import ParseRunRepository
from app.repository.tender_repository import TenderRepository
from app.services.classifier_service import ClassifierService
from app.sources.registry import get_all_codes, get_source_class

logger = logging.getLogger(__name__)


_MAX_ERRORS_IN_MESSAGE = 5


class ParserService:
    """Оркестратор парсинга. Не знает деталей источников и БД — работает
    через абстракции (BaseSource, репозитории, классификатор).
    """

    def __init__(
            self,
            http_client: httpx.AsyncClient,
            tender_repo: TenderRepository,
            parser_run_repo: ParseRunRepository,
            classifier: ClassifierService
    ) -> None:
        self._http_client = http_client
        self._tender_repo = tender_repo
        self._parse_run_repo = parser_run_repo
        self._classifier = classifier

    async def parse_all(self) -> list[ParseSourceResult]:
        """Распарсить все зарегистрированные источники параллельно.

        Падение одного источника не валит остальные — благодаря
        return_exceptions=True в asyncio.gather.

        Returns:
            Список результатов по каждому источнику. Если источник упал
            до создания run_id (например, не нашёлся source_id в БД) —
            он не попадёт в результат, но будет залогирован.
        """
        codes = get_all_codes()
        if not codes:
            logger.warning("Нет зарегистрированных источников — нечего парсить")
            return []

        logger.info("Запуск парсинга %d источников: %s", len(codes), [c.value for c in codes])

        results = await asyncio.gather(
            *(self.parse_source(code) for code in codes),
            return_exceptions=True,
        )

        successful: list[ParseSourceResult] = []
        for code, result in zip(codes, results, strict=True):
            if isinstance(result, BaseException):
                # Сюда попадаем только если упало ДО создания parse_run
                # (например, source_id не найден или нет класса источника)
                logger.error(
                    "Источник %s упал без записи в parse_runs: %r",
                    code.value,
                    result,
                )
            else:
                successful.append(result)
                logger.info(
                    "Источник %s: найдено=%d, сохранено=%d%s",
                    code.value,
                    result.tenders_found,
                    result.tenders_saved,
                    f", ошибка: {result.error_message}" if result.error_message else "",
                )

        return successful

    async def parse_source(self, code: SourceCode) -> ParseSourceResult:
        """
        Распарсить один источник.

        Жизненный цикл:
        1. Резолвим source_id из БД
        2. Создаём запись в parse_runs со статусом 'running'
        3. Получаем класс источника из реестра
        4. Считаем since из последнего успешного запуска
        5. Итерируемся по тендерам, классифицируем, сохраняем
        6. Помечаем запуск как success / partial / failed

        Args:
            code: Код источника для парсинга.

        Returns:
            ParseSourceResult со статистикой.

        Raises:
            ConfigurationError: Если source_id или класс источника не найден.
                Это означает, что ParserService не сможет даже начать работу —
                имеет смысл пробросить наверх, в parse_all эта ошибка
                залогируется через gather(return_exceptions=True).
        """

        source_id = await self._tender_repo.get_source_id_by_code(code=code)

        try:
            source_class = get_source_class(code)
        except ConfigurationError:
            logger.exception("Класс источника %s не зарегистрирован", code.value)
            raise

        run_id = await self._parse_run_repo.create(source_id=source_id)
        logger.info("Старт парсинга %s (run_id=%d)", code.value, run_id)

        source = source_class(http_client=self._http_client)
        since = await self._parse_run_repo.get_last_success_started_at(source_id=source_id)
        if since is not None:
            logger.debug("Парсим %s начиная с %s", code.value, since.isoformat())
        else:
            logger.debug("Парсим %s без since — первый запуск или нет успешных", code.value)

        found = 0
        saved = 0
        errors: list[str] = []

        try:
            async for raw_tender in source.fetch_tenders(since=since):
                found += 1
                try:
                    classified = self._classifier.classify(raw_tender)
                    await self._tender_repo.upsert(classified=classified, source_id=source_id)
                    saved += 1
                except RepositoryError as error:
                    logger.warning(
                        "Не сохранили тендер %s/%s: %s",
                        code.value,
                        raw_tender.external_id,
                        error,
                    )
                    errors.append(f"{raw_tender.external_id}: {error}")
        except SourceError as error:
            # Источник упал целиком (сеть, парсинг, rate limit)
            # Это не "ошибка одного тендера", а провал всего источника
            await self._parse_run_repo.mark_failure(run_id, f"{type(error).__name__}: {error}")
            logger.warning(
                "Источник %s упал (run_id=%d): %s",
                code.value,
                run_id,
                error,
            )
            return ParseSourceResult(
                source_code=code,
                run_id=run_id,
                tenders_found=found,
                tenders_saved=saved,
                error_message=str(error),
            )

        except Exception as error:
            # Неизвестное падение источника
            error_repr = repr(error)
            await self._parse_run_repo.mark_failure(run_id, f"Unexpected: {error_repr}")
            logger.exception(
                "Неожиданная ошибка при парсинге %s (run_id=%d)",
                code.value,
                run_id,
            )
            return ParseSourceResult(
                source_code=code,
                run_id=run_id,
                tenders_found=found,
                tenders_saved=saved,
                error_message=f"Unexpected: {error_repr}",
            )

        if errors:
            error_summary = self._format_errors(errors)
            await self._parse_run_repo.mark_partial(
                run_id=run_id,
                tenders_found=found,
                tenders_saved=saved,
                error_message=error_summary
            )
            return ParseSourceResult(
                source_code=code,
                run_id=run_id,
                tenders_found=found,
                tenders_saved=saved,
                error_message=error_summary,
            )

        await self._parse_run_repo.mark_success(run_id, found, saved)
        return ParseSourceResult(
            source_code=code,
            run_id=run_id,
            tenders_found=found,
            tenders_saved=saved,
        )

    @staticmethod
    def _format_errors(errors: list[str]) -> str:
        """
        Сформировать компактное сообщение из списка ошибок.

        Показываем первые N + общее количество, чтобы не разрастаться до мегабайтов.
        """
        if len(errors) <= _MAX_ERRORS_IN_MESSAGE:
            return "; ".join(errors)
        shown = "; ".join(errors[:_MAX_ERRORS_IN_MESSAGE])
        return f"{shown}; ... и ещё {len(errors) - _MAX_ERRORS_IN_MESSAGE} ошибок"
