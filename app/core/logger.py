import logging
import sys

# from pythonjsonlogger.json import JsonFormatter <- в будущем для k8s чтобы логи были в json формате
from app.config import get_settings

_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "asyncpg",
    "apscheduler",
)

_TEXT_FORMAT = "%(asctime)s | %(name)s | %(levelname)-8s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_JSON_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"

def setup_logging() -> None:
    """Логирование"""
    settings = get_settings()

    level = logging.DEBUG if settings.debug else getattr(logging, settings.log_level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Если setup_logging() случайно вызван второй раз — чистим прошлые хендлеры.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    formatter: logging.Formatter = logging.Formatter(fmt=_TEXT_FORMAT, datefmt=_DATE_FORMAT)
    # if settings.environment == "prod":
    #     formatter = JsonFormatter(_JSON_FORMAT, datefmt=_DATE_FORMAT)
    # else:
    #     formatter = logging.Formatter(_TEXT_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if settings.log_to_file:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = settings.log_dir / "app.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Приглушаем шумные библиотеки
    for noisy in _NOISY_LOGGERS:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Логирование настроено: level=%s, env=%s, file=%s",
        logging.getLevelName(level),
        settings.environment,
        settings.log_to_file,
    )
