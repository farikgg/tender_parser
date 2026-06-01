class ParserError(Exception):
    """Базовое исключение приложения."""


class ConfigurationError(ParserError):
    """Ошибка конфигурации (неправильные настройки, отсутствие токенов и т.п.)."""


class SourceError(ParserError):
    """Базовая ошибка работы с источником."""

    def __init__(self, source_code: str, message: str) -> None:
        self.source_code = source_code
        super().__init__(f"[{source_code}] {message}")


class SourceUnavailableError(SourceError):
    """Источник недоступен (сетевая ошибка, 5xx, таймаут)."""


class SourceParseError(SourceError):
    """Не удалось распарсить ответ источника (изменилась структура и т.п.)."""


class SourceRateLimitError(SourceError):
    """Источник вернул rate limit (429)."""


class RepositoryError(ParserError):
    """Ошибка работы с репозиторием/БД."""
