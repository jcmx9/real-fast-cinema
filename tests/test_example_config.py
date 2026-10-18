from pathlib import Path

from real_fast_cinema.loader import load_global, load_profiles
from real_fast_cinema.sources import available_sources

EXAMPLE = Path(__file__).resolve().parents[1] / "config.example"


def test_example_config_is_valid() -> None:
    config = load_global(EXAMPLE)
    profiles, errors = load_profiles(EXAMPLE)

    assert errors == []
    assert config.smtp is not None
    assert {p.profile.name for p in profiles} == {"krimis-info", "miss-marple-download"}
    for loaded in profiles:
        assert loaded.terms
        assert set(loaded.profile.sources) <= set(available_sources())
