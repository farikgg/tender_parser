"""Источники тендеров.

Импорт классов здесь обязателен — он триггерит декоратор @register_source,
который регистрирует источник в реестре. Без импорта источник "невидим"
для ParserService.
"""

from app.sources.mp_kz import MpKZSource
from app.sources.eurasiantech import EurasianTechSource
from app.sources.mitwork import MitworkSource

__all__ = ["MpKZSource", "EurasianTechSource", "MitworkSource"]
