import logging
import httpx

from bs4 import BeautifulSoup, Tag
from collections.abc import AsyncIterator
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.config import get_settings
from app.core.enums import SourceCode, TenderStatus
from app.core.exceptions import SourceUnavailableError
from app.core.models import RawTender
from app.sources.base import BaseSource
from app.sources.registry import register_source

logger = logging.getLogger(__name__)


_BASE_URL = "https://eurasiantech-tender.kz"
_PURCHASES_ENDPOINT = "https://eurasiantech-tender.kz/Home/Purchases"

_ALMATY_TZ = timezone(timedelta(hours=5))

# Формат даты на eurasiantech: "21.05.2026 15:00:00"
_DATE_FORMAT = "%d.%m.%Y %H:%M:%S"

_SEARCH_KEYWORDS: tuple[str, ...] = (
    "страхование",
    "страхования",
    "ОСАГО",
    "ОГПО",
    "КАСКО",
    "полис",
    "аннуитет",
)


@register_source(SourceCode.EURASIANTECH)
class EurasianTechSource(BaseSource):
    """
    Источник тендеров с ЭТП EurasianTech (eurasiantech-tender.kz).

    Парсит HTML-страницы поиска. Карточки лотов требуют авторизации,
    поэтому доступны только данные из списка: название, сумма, заказчик,
    даты приёма заявок.
    """
    code: ClassVar[SourceCode] = SourceCode.EURASIANTECH

    async def fetch_tenders(
        self,
        since: datetime | None = None,
    ) -> AsyncIterator[RawTender]:
        """
        Получить тендеры с eep eurasiantech-tender.kz через HTML-страницы поиска.

        Для каждого ключевого слова из _SEARCH_KEYWORDS обходит страницы
        результатов поиска (Filter.FilterString). Дубликаты отсекаются
        через seen_ids.

        Параметр `since` игнорируется: стратегия "до знакомого тендера"
        не применяется — обходим до max_pages страниц по каждому ключевику.
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
                url=_PURCHASES_ENDPOINT,
                params={
                    "Filter.PageSize": 20,
                    "Filter.PageNumber": page,
                    "Filter.SortOption": 0,
                    "Filter.FilterString": keyword,
                }
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as error:
            raise SourceUnavailableError(
                source_code=self.code,
                message=f"Не удалось загрузить страницу {page} по запросу '{keyword}'",
            ) from error

    def _parse_page(self, html: str) -> list[RawTender]:
        soup = BeautifulSoup(html, "lxml")

        grid = soup.find("div", id="purchase_grid")
        if grid is None:
            return []

        tbody = grid.find("tbody")
        if tbody is None:
            return []

        rows = tbody.find_all("tr")

        result: list[RawTender] = []
        for row in rows:
            try:
                raw = self._parse_row(row)
            except Exception as error:
                logger.warning("eurasiantech: не удалось распарсить строку: %s", error)
                continue
            result.append(raw)
        return result

    def _parse_row(self, row: Tag) -> RawTender:
        cells = row.find_all("td")

        link = cells[0].find("a")
        href = link.get("href")  # "/Purchase/Index/74922"
        title = link.get_text(strip=True)

        url = f"{_BASE_URL}{href}"
        external_id = href.rstrip("/").split("/")[-1]
        customer_name = cells[2].get_text(strip=True)
        amount = self._parse_amount(cells[1].get_text(strip=True))
        publication_date = self._parse_date(cells[3].get_text(strip=True))
        deadline_date = self._parse_date(cells[4].get_text(strip=True))

        return RawTender(
            source_code=self.code,
            external_id=external_id,
            title=title,
            description=None,
            url=url,
            customer_name=customer_name,
            customer_bin=None,
            amount=amount,
            currency="KZT",
            published_at=publication_date,
            deadline_at=deadline_date,
            status=TenderStatus.UNKNOWN,
            raw_data={"html_row": str(row)},
        )

    @staticmethod
    def _parse_amount(text: str) -> Decimal | None:
        """Превратить строку суммы в Decimal. 'скрыто'/пусто/мусор → None."""
        cleaned = text.replace(" ", "").replace("\xa0", "").strip()
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _parse_date(text: str) -> datetime | None:
        """Распарсить дату формата '21.05.2026 15:00:00' в aware datetime."""
        text = text.strip()
        if not text:
            return None
        try:
            naive = datetime.strptime(text, _DATE_FORMAT)
        except ValueError:
            logger.warning("eurasiantech: не удалось распарсить дату %r", text)
            return None
        return naive.replace(tzinfo=_ALMATY_TZ)
