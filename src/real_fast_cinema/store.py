"""SQLite state: handled films per profile and last run times."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from real_fast_cinema.matching import dedup_key, durations_close
from real_fast_cinema.models import Hit

_SCHEMA = """
CREATE TABLE IF NOT EXISTS handled (
    id INTEGER PRIMARY KEY,
    profile TEXT NOT NULL,
    key TEXT NOT NULL,
    duration INTEGER NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0,
    downloaded INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    path TEXT,
    url TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS handled_profile_key ON handled (profile, key);
CREATE TABLE IF NOT EXISTS runs (
    profile TEXT PRIMARY KEY,
    last_run TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Record:
    """State of one film for one profile."""

    row_id: int
    notified: bool
    downloaded: bool
    attempts: int


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    """Persistent state; ``path=None`` keeps everything in memory."""

    def __init__(self, path: Path | None) -> None:
        if path is None:
            self._db = sqlite3.connect(":memory:")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(path)
        self._db.executescript(_SCHEMA)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Closes the database connection."""
        self._db.close()

    def find(self, profile: str, hit: Hit) -> Record | None:
        """Returns the record of the same film for ``profile``, if any."""
        rows = self._db.execute(
            "SELECT id, duration, notified, downloaded, attempts FROM handled "
            "WHERE profile = ? AND key = ?",
            (profile, dedup_key(hit)),
        ).fetchall()
        for row_id, duration, notified, downloaded, attempts in rows:
            if durations_close(duration, hit.duration):
                return Record(
                    row_id=row_id,
                    notified=bool(notified),
                    downloaded=bool(downloaded),
                    attempts=attempts,
                )
        return None

    def mark_notified(self, profile: str, hit: Hit) -> None:
        """Marks the film as notified."""
        self._update(profile, hit, "notified = 1")

    def mark_downloaded(self, profile: str, hit: Hit, path: Path) -> None:
        """Marks the film as downloaded to ``path``."""
        self._update(
            profile, hit, "downloaded = 1, path = ?, last_error = NULL", str(path)
        )

    def mark_failed(self, profile: str, hit: Hit, error: str) -> int:
        """Records a failed download and returns the number of attempts."""
        row_id = self._update(
            profile, hit, "attempts = attempts + 1, last_error = ?", error
        )
        (attempts,) = self._db.execute(
            "SELECT attempts FROM handled WHERE id = ?", (row_id,)
        ).fetchone()
        return int(attempts)

    def last_run(self, profile: str) -> datetime | None:
        """Start time of the last run of ``profile``."""
        row = self._db.execute(
            "SELECT last_run FROM runs WHERE profile = ?", (profile,)
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def set_last_run(self, profile: str, when: datetime) -> None:
        """Stores the start time of the last run of ``profile``."""
        self._db.execute(
            "INSERT INTO runs (profile, last_run) VALUES (?, ?) "
            "ON CONFLICT (profile) DO UPDATE SET last_run = excluded.last_run",
            (profile, when.isoformat()),
        )
        self._db.commit()

    def _ensure(self, profile: str, hit: Hit) -> int:
        record = self.find(profile, hit)
        if record is not None:
            return record.row_id
        (row_id,) = self._db.execute(
            "INSERT INTO handled (profile, key, duration, url, updated_at) "
            "VALUES (?, ?, ?, ?, ?) RETURNING id",
            (profile, dedup_key(hit), hit.duration, hit.video_url, _now()),
        ).fetchone()
        return int(row_id)

    def _update(self, profile: str, hit: Hit, assignments: str, *params: object) -> int:
        # ``assignments`` is always a constant from this module, never user input.
        row_id = self._ensure(profile, hit)
        self._db.execute(
            f"UPDATE handled SET {assignments}, url = ?, updated_at = ? WHERE id = ?",
            (*params, hit.video_url, _now(), row_id),
        )
        self._db.commit()
        return row_id
