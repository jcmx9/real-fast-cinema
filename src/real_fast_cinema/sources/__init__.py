"""Source registry."""

from collections.abc import Callable

from real_fast_cinema.exceptions import ConfigError
from real_fast_cinema.sources.base import Source
from real_fast_cinema.sources.mediathekviewweb import MediathekViewWeb

_FACTORIES: dict[str, Callable[[], Source]] = {
    MediathekViewWeb.name: MediathekViewWeb,
}


def available_sources() -> list[str]:
    """Names of all registered sources."""
    return sorted(_FACTORIES)


def get_source(name: str) -> Source:
    """Creates the source registered under ``name``.

    Raises:
        ConfigError: If no source has that name.
    """
    try:
        factory = _FACTORIES[name]
    except KeyError:
        available = ", ".join(available_sources())
        raise ConfigError(f"unknown source {name!r} (available: {available})") from None
    return factory()


__all__ = ["Source", "available_sources", "get_source"]
