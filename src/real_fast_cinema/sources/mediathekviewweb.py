"""Source plugin for https://mediathekviewweb.de."""

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from real_fast_cinema import __version__
from real_fast_cinema.exceptions import SourceError
from real_fast_cinema.models import Hit
from real_fast_cinema.text import (
    AD_MARKERS,
    OV_MARKERS,
    SIGN_MARKERS,
    fold,
    split_markers,
)

logger = logging.getLogger(__name__)

NAME = "mediathekviewweb"
API_URL = "https://mediathekviewweb.de/api/query"
PAGE_SIZE = 50
MAX_RESULTS = 500
ATTEMPTS = 3
_TRAILER_WORDS = frozenset({"trailer", "teaser"})
_OV_WORDS = frozenset({"originalversion", "originalfassung"})


def _text(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    return str(value) if value else ""


def to_hit(entry: dict[str, Any]) -> Hit | None:
    """Maps one API entry to a ``Hit``; returns None for unusable entries."""
    hd = _text(entry, "url_video_hd")
    video_url = hd or _text(entry, "url_video") or _text(entry, "url_video_low")
    if not video_url:
        logger.debug("skipping entry %r without video url", entry.get("id"))
        return None
    try:
        duration = int(entry.get("duration") or 0)
        published = datetime.fromtimestamp(int(entry.get("timestamp") or 0), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        logger.debug("skipping malformed entry %r", entry.get("id"))
        return None
    title = _text(entry, "title")
    _, markers = split_markers(title)
    title_words = fold(title).split()
    is_ov = any(m in OV_MARKERS for m in markers) or bool(
        _OV_WORDS.intersection(title_words)
    )
    return Hit(
        source=NAME,
        source_id=_text(entry, "id"),
        channel=_text(entry, "channel"),
        topic=_text(entry, "topic"),
        title=title,
        description=_text(entry, "description"),
        duration=duration,
        published=published,
        video_url=video_url,
        is_hls=".m3u8" in video_url,
        is_hd=bool(hd),
        page_url=_text(entry, "url_website"),
        subtitle_url=_text(entry, "url_subtitle") or None,
        audio_description=any(m in AD_MARKERS for m in markers),
        sign_language=any(m in SIGN_MARKERS for m in markers),
        trailer=bool(title_words) and title_words[0] in _TRAILER_WORDS,
        language="ov" if is_ov else "de",
        year=next((int(m) for m in markers if m.isdigit()), None),
    )


def _parse(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
        if data.get("err"):
            raise SourceError(f"{NAME}: API error: {data['err']}")
        result: dict[str, Any] = data["result"]
        if not isinstance(result["results"], list):
            raise TypeError("'results' is not a list")
        int(result["queryInfo"]["totalResults"])
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise SourceError(f"{NAME}: unexpected response: {exc!r}") from exc
    return result


class MediathekViewWeb:
    """Queries the MediathekViewWeb JSON API."""

    name = NAME

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=30.0,
            headers={"User-Agent": f"real-fast-cinema/{__version__}"},
        )
        self._backoff = backoff
        self._sleep = sleep

    def close(self) -> None:
        """Closes the HTTP client."""
        self._client.close()

    def search(self, term: str) -> list[Hit]:
        """Searches title and topic; paginates up to ``MAX_RESULTS`` entries."""
        hits: list[Hit] = []
        offset = 0
        while offset < MAX_RESULTS:
            result = self._query(term, offset)
            entries: list[Any] = result["results"]
            for entry in entries:
                hit = to_hit(entry) if isinstance(entry, dict) else None
                if hit is not None:
                    hits.append(hit)
            offset += len(entries)
            if not entries or offset >= int(result["queryInfo"]["totalResults"]):
                break
        logger.debug("%s: %r -> %d hits", NAME, term, len(hits))
        return hits

    def _query(self, term: str, offset: int) -> dict[str, Any]:
        body = json.dumps(
            {
                "queries": [{"fields": ["title", "topic"], "query": term}],
                "sortBy": "timestamp",
                "sortOrder": "desc",
                "future": False,
                "offset": offset,
                "size": PAGE_SIZE,
            }
        )
        last_error = ""
        for attempt in range(ATTEMPTS):
            if attempt:
                self._sleep(self._backoff * 2 ** (attempt - 1))
            try:
                response = self._client.post(
                    API_URL, content=body, headers={"Content-Type": "text/plain"}
                )
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                continue
            if response.is_error:
                raise SourceError(f"{NAME}: HTTP {response.status_code}")
            return _parse(response)
        raise SourceError(f"{NAME}: giving up after {ATTEMPTS} attempts ({last_error})")
