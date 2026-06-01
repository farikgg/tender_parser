"""
Pydantic-модели доменной области.

RawTender — "сырой" тендер от источника, ещё не сохранённый в БД.
Tender — тендер из БД (с id и метаданными).
ParseRun — запись о запуске парсинга источника.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.core.enums import ParseRunStatus, SourceCode, TenderStatus


class RawTender(BaseModel):
    """Тендер в том виде, в котором его вернул источник."""

    model_config = ConfigDict(frozen=True)  # неизменяемый — безопаснее в asyncio

    source_code: SourceCode
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1)
    description: str | None = None
    url: HttpUrl
    customer_name: str | None = Field(default=None, max_length=500)
    customer_bin: str | None = Field(default=None, max_length=20)
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="KZT", min_length=3, max_length=3)
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    status: TenderStatus = TenderStatus.UNKNOWN
    raw_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Исходные данные от источника как есть — пригодятся позже",
    )


class Tender(BaseModel):
    """Тендер из БД."""

    model_config = ConfigDict(frozen=True)

    id: int
    source_id: int
    source_code: SourceCode
    external_id: str
    title: str
    description: str | None
    url: str
    customer_name: str | None
    customer_bin: str | None
    amount: Decimal | None
    currency: str
    published_at: datetime | None
    deadline_at: datetime | None
    status: TenderStatus
    is_insurance: bool
    matched_keywords: list[str]
    raw_data: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime


class ClassifiedTender(BaseModel):
    """
    Сырой тендер + результат классификации.
    Промежуточная модель между ClassifierService и Repository.
    """

    model_config = ConfigDict(frozen=True)

    raw: RawTender
    is_insurance: bool
    matched_keywords: list[str] = Field(default_factory=list)


class ParseRun(BaseModel):
    """Запись о запуске парсинга одного источника."""

    model_config = ConfigDict(frozen=True)

    id: int
    source_id: int
    source_code: SourceCode
    started_at: datetime
    finished_at: datetime | None
    status: ParseRunStatus
    tenders_found: int = Field(default=0, ge=0)
    tenders_saved: int = Field(default=0, ge=0)
    error_message: str | None = None


class ParseSourceResult(BaseModel):
    """
    Результат парсинга одного источника. Простой DTO для возврата из parse_source.

    Не Pydantic — валидация не нужна, только удобный возврат значений.
    """

    model_config = ConfigDict(frozen=True)

    source_code: SourceCode
    run_id: int
    tenders_found: int = Field(ge=0)
    tenders_saved: int = Field(ge=0)
    error_message: str | None = None
