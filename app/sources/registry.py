from collections.abc import Callable

from app.core.enums import SourceCode
from app.core.exceptions import ConfigurationError
from app.sources.base import BaseSource


_SOURCE_CLASSES: dict[SourceCode, type[BaseSource]] = {}

def register_source(code: SourceCode) -> Callable[[type[BaseSource]], type[BaseSource]]:
    """Внешняя функция — принимает аргумент декоратора."""

    def decorator(cls: type[BaseSource]) -> type[BaseSource]:
        if code in _SOURCE_CLASSES:
            raise ConfigurationError(
                f"Source class для {code} уже зарегистрирован: "
                f"{_SOURCE_CLASSES[code].__name__}"
            )
        _SOURCE_CLASSES[code] = cls
        return cls

    return decorator

def get_source_class(code: SourceCode) -> type[BaseSource]:
    if code not in _SOURCE_CLASSES:
        raise ConfigurationError(
            f"Source class для {code} не зарегистрирован"
        )
    return _SOURCE_CLASSES[code]

def get_all_codes() -> tuple[SourceCode, ...]:
    return tuple(_SOURCE_CLASSES.keys())
