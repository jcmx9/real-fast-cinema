"""Test helpers (fakes and factories)."""

from datetime import UTC, datetime
from typing import Any

from real_fast_cinema.models import Hit


def make_hit(**overrides: Any) -> Hit:
    values: dict[str, Any] = {
        "source": "fake",
        "source_id": "1",
        "channel": "ARD",
        "topic": "Tatort",
        "title": "Fackel",
        "description": "",
        "duration": 5313,
        "published": datetime(2026, 10, 1, 20, 15, tzinfo=UTC),
        "video_url": "https://cdn.example.org/fackel.mp4",
        "is_hls": False,
        "is_hd": True,
        "page_url": "https://www.example.org/fackel",
        "subtitle_url": None,
    }
    values.update(overrides)
    return Hit(**values)
