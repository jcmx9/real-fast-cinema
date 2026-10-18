import pytest

from real_fast_cinema.exceptions import ConfigError
from real_fast_cinema.sources import available_sources, get_source
from real_fast_cinema.sources.mediathekviewweb import MediathekViewWeb


def test_available_sources_lists_mediathekviewweb() -> None:
    assert available_sources() == ["mediathekviewweb"]


def test_get_source_returns_instance() -> None:
    source = get_source("mediathekviewweb")
    try:
        assert isinstance(source, MediathekViewWeb)
        assert source.name == "mediathekviewweb"
    finally:
        source.close()


def test_get_source_unknown_name() -> None:
    with pytest.raises(ConfigError, match="unknown source 'nope'"):
        get_source("nope")
