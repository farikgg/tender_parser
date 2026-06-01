import asyncio
import logging
import signal

import app.sources

from app.core.logger import setup_logging
from app.infrastructure.database import close_pool, create_pool
from app.infrastructure.ddl import init_schema
from app.infrastructure.http import create_http_client
from app.infrastructure.scheduler import create_cron_trigger, create_scheduler
from app.repository.parse_run_repository import ParseRunRepository
from app.repository.tender_repository import TenderRepository
from app.services.classifier_service import ClassifierService
from app.services.parser_service import ParserService

logger = logging.getLogger(__name__)


async def _run_parsing(parser_service: ParserService) -> None:
    """Обёртка джобы парсинга — вызывается планировщиком по расписанию."""
    logger.info("Плановый запуск парсинга")
    try:
        results = await parser_service.parse_all()
        for result in results:
            logger.info(
                "  %s: найдено=%d, сохранено=%d",
                result.source_code,
                result.tenders_found,
                result.tenders_saved,
            )
    except Exception:
        logger.exception("Плановый парсинг завершился с ошибкой")

async def main() -> None:
    setup_logging()
    logger.info("Запуск garant-tender-parser")

    pool = await create_pool()
    http_client = create_http_client()
    scheduler = create_scheduler()

    try:
        await init_schema(pool)

        parser_service = ParserService(
            http_client=http_client,
            tender_repo=TenderRepository(pool),
            parser_run_repo=ParseRunRepository(pool),
            classifier=ClassifierService(),
        )

        scheduler.add_job(
            func=_run_parsing,
            trigger=create_cron_trigger(),
            args=[parser_service],
            id="parse_all_sources",
        )

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

        scheduler.start()
        logger.info("Сервис запущен, ожидание планового парсинга")
        await stop_event.wait()

        logger.info("Получен сигнал остановки, завершаем работу")
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=True)
        await http_client.aclose()
        await close_pool(pool)
        logger.info("Сервис остановлен")

if __name__ == "__main__":
    asyncio.run(main())
