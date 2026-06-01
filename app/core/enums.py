from enum import StrEnum


class SourceCode(StrEnum):
    """Код источника. Используется как идентификатор в БД и коде."""
    GOSZAKUP = "goszakup"
    MP_KZ = "mp_kz"
    MITWORK = "mitwork"
    EURASIANTECH = "eurasiantech"


class TenderStatus(StrEnum):
    """Статус тендера на площадке."""
    ACTIVE = "active"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ParseRunStatus(StrEnum):
    """Статус запуска парсинга источника."""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"  # часть данных получили, часть — нет
