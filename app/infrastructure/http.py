import logging

from httpx import (
    AsyncClient,
    ConnectError,
    HTTPStatusError,
    Limits,
    PoolTimeout,
    ReadTimeout,
    RemoteProtocolError,
    Response,
    Timeout,
    WriteTimeout,
)
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.core.exceptions import SourceRateLimitError, SourceUnavailableError

logger = logging.getLogger(__name__)
# Сетевые исключения httpx, при которых стоит ретраить
_RETRYABLE_NETWORK_ERRORS: tuple[type[Exception], ...] = (
    ConnectError,
    ReadTimeout,
    WriteTimeout,
    PoolTimeout,
    RemoteProtocolError,
)


def create_http_client() -> AsyncClient:
    settings = get_settings()

    http_client: AsyncClient = AsyncClient(
        timeout=Timeout(settings.http_timeout_seconds),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Safari/605.1.15"
            ),
            "Accept-Language": "ru,en;q=0.9",
        },
        follow_redirects=True,
        limits=Limits(max_connections=100, max_keepalive_connections=20),
    )
    return http_client

def _is_retryable_exception(exc: BaseException) -> bool:
    """
    Определить, стоит ли ретраить запрос при данном исключении.

    Ретраим:
    - Сетевые ошибки (соединение оборвалось, таймаут чтения и т.п.)
    - HTTP 5xx (сервер временно сломан)
    - HTTP 429 (rate limit — но с большой паузой)

    Не ретраим:
    - HTTP 4xx кроме 429 (запрос некорректен, повтор не поможет)
    - Прочие исключения (например, ValueError из нашего кода)
    """

    if isinstance(exc, _RETRYABLE_NETWORK_ERRORS):
        return True

    if isinstance(exc, HTTPStatusError):
        status = exc.response.status_code
        return status >= 500 or status == 429

    return False

async def request_with_retry(
        client: AsyncClient,
        method: str,
        url: str,
        *,
        source_code: str,
        max_retries: int | None = None,
        **kwargs: object,
) -> Response:
    """Выполнить HTTP-запрос с экспоненциальным retry.

    Бросает доменные исключения (SourceUnavailableError / SourceRateLimitError)
    вместо httpx-исключений, чтобы вышестоящий код работал с доменом, а не
    с деталями HTTP-библиотеки.

    Args:
        client: HTTP-клиент.
        method: HTTP-метод ('GET', 'POST', ...).
        url: URL запроса.
        source_code: Код источника для логов и исключений.
        max_retries: Сколько раз повторять (None → из settings).
        **kwargs: Дополнительные параметры для httpx.AsyncClient.request().

    Returns:
        Успешный ответ (raise_for_status уже вызван).

    Raises:
        SourceRateLimitError: При 429 после всех ретраев.
        SourceUnavailableError: При сетевой ошибке или 5xx после всех ретраев.
    """
    settings = get_settings()
    attempts = max_retries if max_retries is not None else settings.http_max_retries

    try:
        async for attempt in AsyncRetrying(
                stop=stop_after_attempt(attempts + 1),  # +1 потому что первая попытка тоже считается
                wait=wait_exponential(multiplier=1, min=1, max=30),
                retry=retry_if_exception(_is_retryable_exception),
                reraise=True,
        ):
            with attempt:
                logger.debug(
                    f"HTTP {method} {url} "
                    f"(попытка {attempt.retry_state.attempt_number}/{attempts + 1}) "
                    f"[{source_code}]",
                )
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response

    except HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise SourceRateLimitError(
                source_code,
                f"Rate limit при {method} {url} (status=429)",
            ) from exc
        raise SourceUnavailableError(
            source_code,
            f"HTTP {exc.response.status_code} при {method} {url}",
        ) from exc

    except _RETRYABLE_NETWORK_ERRORS as exc:
        raise SourceUnavailableError(
            source_code,
            f"Сетевая ошибка при {method} {url}: {type(exc).__name__}",
        ) from exc

    except RetryError as exc:
        # На случай если tenacity всё-таки пробросит RetryError
        # (если reraise=True не сработает по какой-то причине)
        raise SourceUnavailableError(
            source_code,
            f"Превышено число попыток для {method} {url}",
        ) from exc

    # Сюда мы попасть не должны — либо вернули response, либо бросили исключение
    raise SourceUnavailableError(
        source_code,
        f"Неожиданное состояние после retry для {method} {url}",
    )
