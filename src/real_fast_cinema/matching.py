"""Matching of hits against search terms, filters and deduplication."""

from collections.abc import Iterable, Sequence
from datetime import datetime

from real_fast_cinema.config import Filters, Tristate
from real_fast_cinema.models import Hit
from real_fast_cinema.text import display_title, fold, words

MIN_DURATION_TOLERANCE = 60
RELATIVE_DURATION_TOLERANCE = 0.02


def _haystack(hit: Hit) -> set[str]:
    return set(words(f"{hit.topic} {hit.title}"))


def _contains_all(haystack: set[str], phrase: str) -> bool:
    needed = words(phrase)
    return bool(needed) and set(needed) <= haystack


def matches_term(hit: Hit, term: str) -> bool:
    """True if every word of ``term`` occurs in topic and title of ``hit``."""
    return _contains_all(_haystack(hit), term)


def _tristate_ok(value: bool, wanted: Tristate) -> bool:
    return wanted == "any" or value == wanted


def passes_filters(hit: Hit, filters: Filters) -> bool:
    """True if ``hit`` satisfies all profile filters."""
    if (
        filters.min_duration is not None
        and hit.duration < filters.min_duration.total_seconds()
    ):
        return False
    checks = (
        (hit.audio_description, filters.audio_description),
        (hit.sign_language, filters.sign_language),
        (hit.trailer, filters.trailer),
        (hit.subtitle_url is not None, filters.subtitles),
    )
    if not all(_tristate_ok(value, wanted) for value, wanted in checks):
        return False
    if filters.language != "any" and hit.language != filters.language:
        return False
    haystack = _haystack(hit)
    return not any(_contains_all(haystack, entry) for entry in filters.exclude)


def select(hit: Hit, term: str, filters: Filters) -> bool:
    """True if ``hit`` matches ``term`` and passes ``filters``."""
    return matches_term(hit, term) and passes_filters(hit, filters)


def dedup_key(hit: Hit) -> str:
    """Normalized ``topic|title`` key used to recognize the same film."""
    return f"{fold(hit.topic)}|{fold(display_title(hit.topic, hit.title))}"


def durations_close(a: int, b: int) -> bool:
    """True if durations differ by at most ``max(60 s, 2 %)``."""
    tolerance = max(MIN_DURATION_TOLERANCE, RELATIVE_DURATION_TOLERANCE * max(a, b))
    return abs(a - b) <= tolerance


def same_film(a: Hit, b: Hit) -> bool:
    """True if both hits describe the same film."""
    return dedup_key(a) == dedup_key(b) and durations_close(a.duration, b.duration)


def group_hits(hits: Iterable[Hit]) -> list[list[Hit]]:
    """Groups hits of the same film, keeping first-seen order."""
    groups: list[list[Hit]] = []
    for hit in hits:
        for group in groups:
            if same_film(group[0], hit):
                group.append(hit)
                break
        else:
            groups.append([hit])
    return groups


def _rank(hit: Hit) -> tuple[bool, bool, bool, bool, datetime]:
    return (
        not hit.is_hls,
        hit.is_hd,
        not hit.audio_description,
        not hit.sign_language,
        hit.published,
    )


def best_hit(group: Sequence[Hit]) -> Hit:
    """Best hit of a group: MP4 before HLS, HD, plain version, newest."""
    return max(group, key=_rank)
