from datetime import UTC, datetime
from typing import Any

import pytest

from real_fast_cinema.config import Filters
from real_fast_cinema.matching import (
    best_hit,
    dedup_key,
    durations_close,
    group_hits,
    matches_term,
    passes_filters,
    same_film,
    select,
)
from tests.fakes import make_hit


@pytest.mark.parametrize(
    ("term", "topic", "title", "expected"),
    [
        ("Miss Marple", "Miss Marple", "16 Uhr 50 ab Paddington", True),
        ("miss marple", "Krimi", "Marple, Miss - Mord im Pfarrhaus", True),
        ("Miss Marple", "Krimi", "Miss Marples Rache", False),
        ("Deja vu", "Tatort", "Déjà-vu", True),
        ("Tatort Unter Freunden", "Tatort", "Tatort: Unter Freunden", True),
        ("Tatort Fackel", "Polizeiruf 110", "Fackel", False),
        ("", "Tatort", "Fackel", False),
    ],
)
def test_matches_term_requires_all_words(
    term: str, topic: str, title: str, expected: bool
) -> None:
    assert matches_term(make_hit(topic=topic, title=title), term) is expected


@pytest.mark.parametrize(
    ("hit_overrides", "filters", "expected"),
    [
        ({}, {}, True),
        ({"duration": 37}, {"min_duration": "60m"}, False),
        ({"duration": 3600}, {"min_duration": "60m"}, True),
        ({"audio_description": True}, {}, False),
        ({"audio_description": True}, {"audio_description": True}, True),
        ({}, {"audio_description": True}, False),
        ({"audio_description": True}, {"audio_description": "any"}, True),
        ({"sign_language": True}, {}, False),
        ({"trailer": True}, {}, False),
        ({"trailer": True}, {"trailer": "any"}, True),
        ({}, {"subtitles": True}, False),
        ({"subtitle_url": "https://x/s.vtt"}, {"subtitles": True}, True),
        ({"subtitle_url": "https://x/s.vtt"}, {"subtitles": False}, False),
        ({"language": "ov"}, {"language": "de"}, False),
        ({"language": "ov"}, {"language": "ov"}, True),
        ({"language": "ov"}, {}, True),
        ({"title": "Trailer: Fackel"}, {"exclude": ["Trailer"]}, False),
        ({"title": "Fackel - die Doku"}, {"exclude": ["die Doku"]}, False),
        ({"title": "Die Fackel"}, {"exclude": ["die Doku"]}, True),
        ({}, {"exclude": ["", "  "]}, True),
    ],
)
def test_passes_filters(
    hit_overrides: dict[str, Any], filters: dict[str, Any], expected: bool
) -> None:
    hit = make_hit(**hit_overrides)

    assert passes_filters(hit, Filters.model_validate(filters)) is expected


def test_select_combines_match_and_filters() -> None:
    hit = make_hit(title="Fackel (Audiodeskription)", audio_description=True)

    assert select(make_hit(), "Tatort Fackel", Filters()) is True
    assert select(hit, "Tatort Fackel", Filters()) is False
    assert select(make_hit(), "Polizeiruf", Filters()) is False


@pytest.mark.parametrize(
    ("topic", "title", "key"),
    [
        ("Tatort", "Tatort: Unter Freunden", "tatort|unter freunden"),
        ("Tatort", "Unter Freunden", "tatort|unter freunden"),
        ("Tatort", "Fackel (Audiodeskription)", "tatort|fackel"),
        ("Tatort", "Trailer: Fackel", "tatort|trailer fackel"),
        ("Tatort", "Cash (2024)", "tatort|cash"),
    ],
)
def test_dedup_key(topic: str, title: str, key: str) -> None:
    assert dedup_key(make_hit(topic=topic, title=title)) == key


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (5170, 5170, True),
        (5170, 5229, True),
        (5170, 5300, False),
        (6000, 6110, True),
        (6000, 6130, False),
        (30, 85, True),
    ],
)
def test_durations_close(a: int, b: int, expected: bool) -> None:
    assert durations_close(a, b) is expected


def test_same_film_needs_key_and_duration() -> None:
    ndr = make_hit(title="Unter Freunden", duration=5170)
    orf = make_hit(title="Tatort: Unter Freunden", duration=5170, channel="ORF")
    short = make_hit(title="Unter Freunden", duration=600)

    assert same_film(ndr, orf) is True
    assert same_film(ndr, short) is False
    assert same_film(ndr, make_hit(title="Fackel", duration=5170)) is False


def test_group_hits_and_best_hit_prefer_mp4_hd_plain_newest() -> None:
    ndr = make_hit(source_id="ndr", title="Unter Freunden", duration=5170)
    orf = make_hit(
        source_id="orf",
        title="Tatort: Unter Freunden",
        duration=5170,
        is_hls=True,
        video_url="https://orf.example/chunklist.m3u8",
    )
    ad = make_hit(
        source_id="ad",
        title="Unter Freunden (Audiodeskription)",
        duration=5170,
        audio_description=True,
        published=datetime(2026, 10, 9, tzinfo=UTC),
    )
    low = make_hit(source_id="low", title="Unter Freunden", duration=5170, is_hd=False)
    other = make_hit(source_id="fackel", title="Fackel")

    groups = group_hits([orf, ad, low, ndr, other])

    assert [[h.source_id for h in g] for g in groups] == [
        ["orf", "ad", "low", "ndr"],
        ["fackel"],
    ]
    assert best_hit(groups[0]).source_id == "ndr"
    assert best_hit(groups[1]).source_id == "fackel"


def test_best_hit_newest_wins_on_tie() -> None:
    old = make_hit(source_id="old", published=datetime(2026, 1, 1, tzinfo=UTC))
    new = make_hit(source_id="new", published=datetime(2026, 9, 1, tzinfo=UTC))

    assert best_hit([old, new]).source_id == "new"
