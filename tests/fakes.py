"""Test helpers (fakes and factories)."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from real_fast_cinema.config import DownloadOpts, GlobalConfig, Profile
from real_fast_cinema.exceptions import DownloadError, NotifyError
from real_fast_cinema.loader import LoadedProfile
from real_fast_cinema.models import Hit, Report
from real_fast_cinema.runner import RunContext
from real_fast_cinema.sources.base import Source
from real_fast_cinema.store import Store


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


NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class FakeSource:
    def __init__(
        self,
        name: str = "fake",
        results: dict[str, list[Hit]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.results = results or {}
        self.error = error
        self.queries: list[str] = []
        self.closed = False

    def search(self, term: str) -> list[Hit]:
        self.queries.append(term)
        if self.error is not None:
            raise self.error
        return list(self.results.get(term, []))

    def close(self) -> None:
        self.closed = True


class FakeNotifier:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[Report, list[str]]] = []

    def send(self, report: Report, recipients: Sequence[str]) -> None:
        if self.fail:
            raise NotifyError("smtp down")
        self.sent.append((report, list(recipients)))


class FakeDownloader:
    def __init__(self, root: Path, fail: bool = False) -> None:
        self.root = root
        self.fail = fail
        self.calls: list[Hit] = []

    def download(self, hit: Hit, opts: DownloadOpts) -> Path:
        self.calls.append(hit)
        if self.fail:
            raise DownloadError("connection reset")
        return self.root / opts.target / f"{hit.source_id}.mp4"


def make_ctx(
    tmp_path: Path,
    *,
    sources: dict[str, Source] | Callable[[str], Source],
    notifier: FakeNotifier | None = None,
    downloader: FakeDownloader | None = None,
    dry_run: bool = False,
    max_retries: int = 3,
) -> RunContext:
    config = GlobalConfig.model_validate(
        {
            "data_dir": tmp_path / "data",
            "downloads_root": tmp_path / "media",
            "mail_to": ["me@example.org"],
            "defaults": {"max_retries": max_retries},
        }
    )
    resolver = sources if callable(sources) else sources.__getitem__
    return RunContext(
        config=config,
        store=Store(None),
        sources=resolver,
        downloader=downloader or FakeDownloader(tmp_path),
        notifier=notifier,
        dry_run=dry_run,
        now=lambda: NOW,
    )


def make_profile(**overrides: Any) -> LoadedProfile:
    terms = tuple(overrides.pop("terms", ("Tatort Fackel",)))
    data: dict[str, Any] = {
        "name": "test",
        "sources": ["fake"],
        "titles": "t.txt",
        "action": "info",
    }
    data.update(overrides)
    if data["action"] != "info":
        data.setdefault("download", {"target": "filme"})
    return LoadedProfile(
        profile=Profile.model_validate(data), terms=terms, path=Path("test.yaml")
    )
