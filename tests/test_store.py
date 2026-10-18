from datetime import UTC, datetime
from pathlib import Path

from real_fast_cinema.store import Record, Store
from tests.fakes import make_hit


def test_find_unknown_returns_none() -> None:
    with Store(None) as store:
        assert store.find("p", make_hit()) is None


def test_mark_notified_is_found_again() -> None:
    hit = make_hit()
    with Store(None) as store:
        store.mark_notified("p", hit)

        record = store.find("p", hit)

    assert record is not None
    assert (record.notified, record.downloaded, record.attempts) == (True, False, 0)


def test_find_matches_same_film_from_other_channel() -> None:
    ndr = make_hit(title="Unter Freunden", duration=5170)
    orf = make_hit(title="Tatort: Unter Freunden", duration=5200, channel="ORF")
    with Store(None) as store:
        store.mark_notified("p", ndr)

        assert store.find("p", orf) is not None
        assert store.find("p", make_hit(title="Unter Freunden", duration=600)) is None


def test_profiles_are_independent() -> None:
    hit = make_hit()
    with Store(None) as store:
        store.mark_notified("a", hit)

        assert store.find("b", hit) is None


def test_mark_failed_counts_attempts_and_download_resets_nothing_else() -> None:
    hit = make_hit()
    with Store(None) as store:
        assert store.mark_failed("p", hit, "timeout") == 1
        assert store.mark_failed("p", hit, "timeout") == 2
        store.mark_downloaded("p", hit, Path("/media/x.mp4"))

        record = store.find("p", hit)

    assert record == Record(
        row_id=record.row_id if record else 0,
        notified=False,
        downloaded=True,
        attempts=2,
    )


def test_one_row_per_film() -> None:
    hit = make_hit()
    with Store(None) as store:
        store.mark_failed("p", hit, "x")
        store.mark_notified("p", hit)
        store.mark_downloaded("p", hit, Path("/m/x.mp4"))

        rows = store._db.execute("SELECT COUNT(*) FROM handled").fetchone()

    assert rows == (1,)


def test_state_persists_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "data" / "state.db"
    hit = make_hit()
    with Store(db) as store:
        store.mark_notified("p", hit)

    with Store(db) as store:
        assert store.find("p", hit) is not None


def test_last_run_roundtrip() -> None:
    when = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    with Store(None) as store:
        assert store.last_run("p") is None
        store.set_last_run("p", when)
        store.set_last_run("p", when.replace(hour=13))

        assert store.last_run("p") == when.replace(hour=13)
