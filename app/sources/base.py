from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from typing import ClassVar

from httpx import AsyncClient

from app.core.enums import SourceCode
from app.core.models import RawTender


class BaseSource(ABC):
    """
    Абстрактный источник тендеров.

    Наследники должны:
    1. Задать атрибут класса `code` — соответствующий SourceCode.
    2. Реализовать `fetch_tenders` как async-генератор.

    Пример:
        class GoszakupSource(BaseSource):
            code: ClassVar[SourceCode] = SourceCode.GOSZAKUP

            async def fetch_tenders(self, since=None):
                response = await self._http.get(...)
                for item in response.json()["items"]:
                    yield RawTender(...)
    """
    code: ClassVar[SourceCode]

    def __init__(self, http_client: AsyncClient) -> None:
        self._http_client = http_client

    @abstractmethod
    def fetch_tenders(self, since: datetime | None) -> AsyncIterator[RawTender]:
        """
        Получить тендеры с источника.

        Реализация должна быть async-генератором — использовать `yield`
        для каждого тендера. Это позволяет потоково обрабатывать большие
        выборки без загрузки всех тендеров в память.

        Стратегия пагинации:
        - Если `since` задан — возвращать тендеры опубликованные после
          этой даты (рекомендуется для источников с поддержкой
          фильтрации по дате, например goszakup).
        - Если `since` равен None — реализация выбирает стратегию сама.
          Например, обходить страницы до встречи с уже знакомым тендером
          (для HTML-источников без фильтра по дате).

        Args:
            since: Нижняя граница даты публикации тендеров. None означает
                "первый запуск" или "стратегия по умолчанию".

        Yields:
            RawTender — сырой тендер от площадки, ещё не классифицированный
            и не сохранённый в БД.

        Raises:
            SourceUnavailableError: Источник недоступен — сетевая ошибка,
                HTTP 5xx, таймаут. Парсинг следует прервать, повторим
                в следующем запуске.
            SourceParseError: Структура ответа источника отличается от
                ожидаемой. Сигнал, что вёрстка/API площадки изменились
                и парсер нужно поправить.
            SourceRateLimitError: Источник попросил притормозить (HTTP 429).
                Парсинг прерывается, при следующем запуске повторим.
        """
        ...
