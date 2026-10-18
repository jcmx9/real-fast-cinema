"""Domain models shared by all components."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

Language = Literal["de", "ov"]


@dataclass(frozen=True, slots=True)
class Hit:
    """A normalized search result of any source."""

    source: str
    source_id: str
    channel: str
    topic: str
    title: str
    description: str
    duration: int
    published: datetime
    video_url: str
    is_hls: bool
    is_hd: bool
    page_url: str
    subtitle_url: str | None
    audio_description: bool = False
    sign_language: bool = False
    trailer: bool = False
    language: Language = "de"
    year: int | None = None


@dataclass(frozen=True, slots=True)
class Failure:
    """A failed download attempt."""

    hit: Hit
    error: str
    attempts: int
    final: bool


@dataclass(slots=True)
class Report:
    """Outcome of one profile run."""

    profile: str
    found: list[Hit] = field(default_factory=list)
    planned: list[Hit] = field(default_factory=list)
    downloaded: list[tuple[Hit, Path]] = field(default_factory=list)
    failed: list[Failure] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Returns a one-line summary such as ``2 found, 0 downloaded, 0 failed``."""
        text = (
            f"{len(self.found)} found, {len(self.downloaded)} downloaded, "
            f"{len(self.failed)} failed"
        )
        if self.errors:
            text += f", {len(self.errors)} source errors"
        return text
