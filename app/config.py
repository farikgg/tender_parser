from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Глобальные настройки приложения."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # Окружение
    environment: Literal["dev", "qa", "prod"] = Field(default="dev")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    debug: bool = Field(default=False, validation_alias="APP_DEBUG")

    # База данных
    database_url: str = Field(
        description="URL для подключения к PostgreSQL",
    )
    db_schema: str = Field(default="tender_parser")
    db_pool_min_size: int = Field(default=2, ge=1)
    db_pool_max_size: int = Field(default=10, ge=1)
    db_command_timeout: float = Field(default=30.0, gt=0)
    db_inactive_lifetime: float = Field(default=300.0, gt=0)

    # HTTP-клиент
    http_timeout_seconds: float = Field(default=30.0, gt=0)
    http_max_retries: int = Field(default=3, ge=0)
    http_user_agent: str = Field(
        default="garant-tender-parser/0.1",
    )

    # Scheduler
    scheduler_timezone: str = Field(default="Asia/Almaty")
    scheduler_cron_hour: str = Field(default="9-17")
    scheduler_cron_day_of_week: str = Field(default="mon-fri")

    # Парсер
    parser_max_pages_per_source: int = Field(
        default=10,
        ge=1,
        description="Сколько страниц максимум обходить у HTML-источников за один запуск",
    )

    # Logger
    log_dir: Path = Field(default=Path("logs"))
    log_to_file: bool = Field(default=False)

@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
