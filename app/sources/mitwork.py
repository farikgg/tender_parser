import logging
import httpx

from bs4 import BeautifulSoup, Tag
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.config import get_settings
from app.core.enums import SourceCode, TenderStatus
from app.core.exceptions import SourceUnavailableError
from app.core.models import RawTender
from app.sources.base import BaseSource
from app.sources.registry import register_source

logger = logging.getLogger(__name__)


_LOTS_ENDPOINT = "https://eep.mitwork.kz/ru/publics/lots"
_LOT_URL_TEMPLATE = "https://eep.mitwork.kz/ru/publics/lot/{lot_id}"


_SEARCH_KEYWORDS: tuple[str, ...] = (
    "страхование",
    # TODO: Ключевые слова для поиска. Начинаем с одного — расширю после первого теста.
)

_STATUS_MAP: dict[str, TenderStatus] = {
    "Опубликован": TenderStatus.ACTIVE,
    "Итоги. Закупка состоялась": TenderStatus.CLOSED,
    "Итоги. Закупка не состоялась": TenderStatus.CLOSED,
    "Завершено": TenderStatus.CLOSED,
    "Отменен": TenderStatus.CANCELLED,
}


@register_source(SourceCode.MITWORK)
class MitworkSource(BaseSource):
    """
    Источник тендеров с Евразийского электронного портала (eep.mitwork.kz).

    Парсит HTML-страницы поиска по лотам. Поиск ведётся по страховым
    ключевым словам — сайт сам фильтрует выдачу, что резко сокращает
    объём обхода.
    """
    code: ClassVar[SourceCode] = SourceCode.MITWORK

    async def fetch_tenders(
        self,
        since: datetime | None = None
    ) -> AsyncIterator[RawTender]:
        """
        Получить лоты с eep.mitwork.kz через HTML-страницы поиска.

        Для каждого ключевого слова из _SEARCH_KEYWORDS обходит страницы
        результатов поиска. Сайт сам фильтрует выдачу по ключевику.
        Дубликаты (один лот найден по разным словам) отсекаются через seen_ids.

        Параметр `since` игнорируется: в списке mitwork нет даты публикации,
        сравнивать не с чем. Источник всегда обходит до max_pages страниц.
        """
        settings = get_settings()
        max_pages = settings.parser_max_pages_per_source
        seen_ids: set[str] = set()

        for keyword in _SEARCH_KEYWORDS:
            page = 1
            while page <= max_pages:
                html = await self._fetch_page(keyword=keyword, page=page)
                tenders = self._parse_page(html)

                if not tenders:
                    # если по ключевому слову не нашлось тендеров идем к следующему
                    break

                for raw in tenders:
                    if raw.external_id in seen_ids:
                        continue
                    seen_ids.add(raw.external_id)
                    yield raw

                page += 1

    async def _fetch_page(self, keyword: str, page: int) -> str:
        try:
            response = await self._http_client.get(
                url=_LOTS_ENDPOINT,
                params={
                    "filter[search]": keyword,
                    "filter[lot_status]": "EMPTY",
                    "filter[is_preliminary]": "EMPTY",
                    "page": page,
                    "per-page": 50,
                }
            )
            # logger.info("mitwork URL: %s", response.url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as error:
            raise SourceUnavailableError(
                source_code=self.code,
                message=f"Не удалось загрузить страницу {page} по запросу '{keyword}'",
            ) from error

    def _parse_page(self, html: str) -> list[RawTender]:
        soup = BeautifulSoup(html, "lxml")

        rows = soup.find_all("tr", class_="item")
        result: list[RawTender] = []
        for row in rows:
            try:
                raw = self._parse_row(row)
            except Exception as error:
                logger.warning("mitwork: не удалось распарсить строку: %s", error)
                continue
            result.append(raw)

        return result

    def _parse_row(self, row: Tag) -> RawTender:
        cells = row.find_all("td")

        external_id = str(row.get("data-key"))

        link = row.find("a", class_="word-break")
        title = link.get_text(strip=True)
        lot_path = link.get("href")

        ktru_span = cells[1].find("span", class_="label")
        ktru = ktru_span.get_text(strip=True) if ktru_span else None

        extra = cells[2].get_text(strip=True) or None

        # description — склейка extra + КТРУ
        desc_parts = [p for p in (extra, ktru) if p]
        description = " | ".join(desc_parts) or None

        amount = self._parse_amount(cells[3].get_text(strip=True))

        customer_link = cells[4].find("a")
        customer_bin = customer_link.get_text(strip=True) if customer_link else None
        customer_name = customer_link.get("title") if customer_link else None

        status = self._map_status(cells[5].get_text(strip=True))

        return RawTender(
            source_code=self.code,
            external_id=external_id,
            title=title,
            description=description,
            url=lot_path,
            customer_name=customer_name,
            customer_bin=customer_bin,
            amount=amount,
            currency="KZT",
            published_at=None,
            deadline_at=None,
            status=status,
            raw_data={"html_row": str(row)},
        )

    @staticmethod
    def _parse_amount(text: str) -> Decimal | None:
        """
        Превратить строку суммы mitwork в Decimal.

        Вход: '18 200 000,00 KZT' → Decimal('18200000.00').
        Мусор ('не указана', пусто) → None.
        """
        cleaned = (
            text.replace(" ", "")
            .replace("\xa0", "")
            .replace("KZT", "")
            .replace(",", ".")
            .strip()
        )

        if not cleaned:
            return None

        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _map_status(text: str) -> TenderStatus:
        """Смаппить статус mitwork.kz в наш TenderStatus."""
        status = _STATUS_MAP.get(text or "")
        if status is None:
            logger.warning("mitwork: неизвестный статус %r", text)
            return TenderStatus.UNKNOWN
        return status
