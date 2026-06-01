import logging
import httpx
import json

from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from app.config import get_settings
from app.core.enums import SourceCode, TenderStatus
from app.core.exceptions import SourceParseError, SourceUnavailableError
from app.core.models import RawTender
from app.sources.base import BaseSource
from app.sources.registry import register_source

logger = logging.getLogger(__name__)


_BASE_URL = "https://mp.kz"
_TENDERS_ENDPOINT = "https://mp.kz/tenders/"
_JSON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}
JSON_KEY_NAME = "data"

_MAPPING_STATUS = {
    "OPEN_FOR_BID": TenderStatus.ACTIVE,
    # TODO: другие значения добавим, когда встретим
}


@register_source(code=SourceCode.MP_KZ)
class MpKZSource(BaseSource):
    """
    Источник тендеров с площадки mp.kz.

    Использует внутренний JSON-API площадки (view=lot).
    Каждый элемент ответа — отдельный лот, который мы сохраняем
    как самостоятельную единицу.
    """
    code: ClassVar[SourceCode] = SourceCode.MP_KZ

    async def fetch_tenders(self, since: datetime | None = None) -> AsyncIterator[RawTender]:
        """
        Получить лоты с mp.kz через внутренний JSON-API.

        Идёт постранично (sort=2 — новые сначала). Если задан `since`,
        останавливается на первом лоте старше этой даты — дальше только
        старее. Битые лоты пропускаются с warning, не валят весь источник.
        """
        settings = get_settings()
        max_pages = settings.parser_max_pages_per_source
        page = 1

        while page <= max_pages:
            lots = await self._fetch_page(page=page)

            if not lots:
                return

            for lot in lots:
                try:
                    raw_tender = self._parse_lot(lot)
                except KeyError as error:
                    logger.warning(
                        f"mp.kz: Не удалось распарсить лот на странице {page}. Ошибка: {error}",
                    )
                    continue

                if since is not None and raw_tender.published_at is not None:
                    if raw_tender.published_at < since:
                        logger.info(f"Достигнут Тендер старше {since}")
                        return

                yield raw_tender
            page += 1

    async def _fetch_page(self, page: int) -> list[dict[str, Any]]:
        """Парсим определенную страницу и создаем Lot (сырой тендер)"""
        try:
            response = await self._http_client.get(
                url=_TENDERS_ENDPOINT,
                headers=_JSON_HEADERS,
                params={"sort": 2, "page": page, "view": "lot"}
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SourceUnavailableError(
                source_code=self.code,
                message=f"Не удалось загрузить страницу {page}",
            ) from error

        try:
            data = response.json()
        except json.JSONDecodeError as error:
            raise SourceParseError(
                source_code=self.code,
                message=f"Невалидный JSON в ответе. Страница: {page}"
            ) from error

        if JSON_KEY_NAME not in data:
            raise SourceParseError(
                source_code=self.code,
                message=f"В ответе нет ключа '{JSON_KEY_NAME}'. Страница: {page}",
            )
        return data[JSON_KEY_NAME]

    def _parse_lot(self, lot: dict[str, Any]) -> RawTender:
        """Переводим сырой Лот в нужный формат"""
        tender = lot.get("Tender") or {}
        company = tender.get("InitiatorCompany") or {}
        customer_name = company.get("name")
        identity = company.get("identity")
        customer_bin = str(identity) if identity is not None else None

        category = lot.get("Category") or {}

        currency = lot.get("Currency") or {}
        currency_code = currency.get("code") or "KZT"

        date_start_raw = lot.get("dateStart")
        published_at = datetime.fromisoformat(date_start_raw) if date_start_raw else None

        date_stop_raw = lot.get("dateStop")
        deadline_at = datetime.fromisoformat(date_stop_raw) if date_stop_raw else None

        tender_url_path = lot.get("tenderUrl") or ""
        url = f"{_BASE_URL}{tender_url_path}"

        amount = self._parse_amount(lot.get("volume"))

        state = lot.get("State") or {}
        status = self._map_status(state.get("constant"))

        description_parts = []
        if tender.get("name"):
            description_parts.append(tender["name"])
        if category.get("name"):
            description_parts.append(category["name"])
        description = " | ".join(description_parts) or None

        raw_tender = RawTender(
            source_code=self.code,
            external_id=str(lot["id"]),
            title=lot["name"],
            description=description,
            url=url,
            customer_name=customer_name,
            customer_bin=customer_bin,
            amount=amount,
            currency=currency_code,
            published_at=published_at,
            deadline_at=deadline_at,
            status=status,
            raw_data=lot,
        )
        return raw_tender

    @staticmethod
    def _map_status(state_constant: str | None) -> TenderStatus:
        """Смаппить статус mp.kz в наш TenderStatus."""
        return _MAPPING_STATUS.get(state_constant or "", TenderStatus.UNKNOWN)

    @staticmethod
    def _parse_amount(value: Any) -> Decimal | None:
        """Безопасно превратить volume в Decimal. Мусор/None → None."""
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
