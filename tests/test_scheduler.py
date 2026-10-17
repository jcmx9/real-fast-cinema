from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from real_fast_cinema.config import GlobalConfig
from real_fast_cinema.exceptions import ConfigError
from real_fast_cinema.runner import RunContext
from real_fast_cinema.scheduler import (
    due_profiles,
    run_daemon,
    seconds_until_next,
    tick,
)
from real_fast_cinema.store import Store
from tests.fakes import (
    NOW,
    FakeDownloader,
    FakeEvent,
    FakeNotifier,
    FakeSource,
    make_ctx,
    make_hit,
    make_profile,
)

SIX_HOURS = timedelta(hours=6)


def test_due_profiles_respects_per_profile_interval() -> None:
    store = Store(None)
    a = make_profile(name="a")
    b = make_profile(name="b", every="1h")
    c = make_profile(name="c")
    store.set_last_run("a", NOW - timedelta(hours=7))
    store.set_last_run("b", NOW - timedelta(minutes=30))

    due = due_profiles([a, b, c], store, SIX_HOURS, NOW)

    assert [p.profile.name for p in due] == ["a", "c"]


def test_seconds_until_next() -> None:
    store = Store(None)
    a = make_profile(name="a")
    b = make_profile(name="b", every="1h")
    store.set_last_run("a", NOW)
    store.set_last_run("b", NOW - timedelta(minutes=30))

    assert seconds_until_next([a, b], store, SIX_HOURS, NOW) == 1800.0
    assert (
        seconds_until_next([a, b, make_profile(name="new")], store, SIX_HOURS, NOW)
        == 0.0
    )
    assert seconds_until_next([], store, SIX_HOURS, NOW) == float("inf")


def test_seconds_until_next_never_negative() -> None:
    store = Store(None)
    store.set_last_run("a", NOW - timedelta(days=2))

    assert seconds_until_next([make_profile(name="a")], store, SIX_HOURS, NOW) == 0.0


def test_tick_runs_due_profiles_and_records_last_run_even_on_failure(
    tmp_path: Path,
) -> None:
    source = FakeSource(results={"Tatort Fackel": [make_hit()]})

    def resolver(name: str) -> FakeSource:
        if name == "missing":
            raise ConfigError("unknown source 'missing'")
        return source

    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, sources=resolver, notifier=notifier)
    good = make_profile(name="good")
    broken = make_profile(name="broken", sources=["missing"])

    delay = tick(ctx, [good, broken])

    assert ctx.store.last_run("good") == NOW
    assert ctx.store.last_run("broken") == NOW
    assert len(notifier.sent) == 1
    assert delay == SIX_HOURS.total_seconds()


def test_tick_survives_unexpected_exceptions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def resolver(name: str) -> FakeSource:
        raise RuntimeError("bug")

    ctx = make_ctx(tmp_path, sources=resolver)

    tick(ctx, [make_profile(name="crashy")])

    assert ctx.store.last_run("crashy") == NOW
    assert "crashy crashed" in caplog.text


def _open_ctx_factory(tmp_path: Path, store: Store) -> Any:
    @contextmanager
    def open_ctx(config: GlobalConfig) -> Iterator[RunContext]:
        yield RunContext(
            config=config,
            store=store,
            sources=lambda name: FakeSource(name=name),
            downloader=FakeDownloader(tmp_path),
            notifier=FakeNotifier(),
            now=lambda: NOW,
        )

    return open_ctx


def test_run_daemon_loops_until_stopped(config_dir: Path, tmp_path: Path) -> None:
    store = Store(None)
    stop = FakeEvent(iterations=2)

    run_daemon(config_dir, _open_ctx_factory(tmp_path, store), stop)

    assert stop.delays == [300.0, 300.0]
    assert store.last_run("krimis") == NOW


def test_run_daemon_uses_short_delay_when_profile_due_soon(
    config_dir: Path, tmp_path: Path
) -> None:
    store = Store(None)
    store.set_last_run("krimis", NOW - SIX_HOURS + timedelta(seconds=42))
    stop = FakeEvent(iterations=1)

    run_daemon(config_dir, _open_ctx_factory(tmp_path, store), stop)

    assert stop.delays == [42.0]


def test_run_daemon_survives_config_errors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    stop = FakeEvent(iterations=1)

    run_daemon(tmp_path, _open_ctx_factory(tmp_path, Store(None)), stop)

    assert stop.delays == [300.0]
    assert "configuration file not found" in caplog.text


def test_run_daemon_logs_broken_profiles(
    config_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (config_dir / "profiles" / "broken.yaml").write_text("name: [", encoding="utf-8")
    stop = FakeEvent(iterations=1)

    run_daemon(config_dir, _open_ctx_factory(tmp_path, Store(None)), stop)

    assert "broken.yaml" in caplog.text


def test_run_daemon_survives_unexpected_errors(
    config_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    @contextmanager
    def failing(config: GlobalConfig) -> Iterator[RunContext]:
        raise OSError("disk gone")
        yield  # pragma: no cover

    stop = FakeEvent(iterations=2)

    run_daemon(config_dir, failing, stop)

    assert stop.delays == [300.0, 300.0]
    assert "daemon iteration failed" in caplog.text
    assert "disk gone" in caplog.text
