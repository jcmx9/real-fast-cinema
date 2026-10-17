import dataclasses
import logging
from pathlib import Path

import pytest

from real_fast_cinema.config import GlobalConfig
from real_fast_cinema.exceptions import ConfigError, SourceError
from real_fast_cinema.models import Report
from real_fast_cinema.notifiers.email import EmailNotifier
from real_fast_cinema.runner import open_context, run_profile, should_notify
from tests import fakes
from tests.fakes import (
    FakeDownloader,
    FakeNotifier,
    FakeSource,
    make_ctx,
    make_hit,
    make_profile,
)

FACKEL = make_hit(source_id="f1", title="Fackel")
FACKEL_AD = make_hit(
    source_id="f2", title="Fackel (Audiodeskription)", audio_description=True
)
FREUNDE = make_hit(source_id="u1", title="Unter Freunden", duration=5170)


def _fackel_source() -> FakeSource:
    return FakeSource(results={"Tatort Fackel": [FACKEL, FACKEL_AD]})


def test_info_notifies_once_per_film(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, sources={"fake": _fackel_source()}, notifier=notifier)
    profile = make_profile()

    first = run_profile(ctx, profile)
    second = run_profile(ctx, profile)

    assert first.found == [FACKEL]
    assert second.found == []
    assert len(notifier.sent) == 1
    assert notifier.sent[0][1] == ["me@example.org"]


def test_profile_recipients_override_global(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, sources={"fake": _fackel_source()}, notifier=notifier)

    run_profile(ctx, make_profile(mail_to=["other@example.org"]))

    assert notifier.sent[0][1] == ["other@example.org"]


def test_failed_mail_is_retried_next_run(tmp_path: Path) -> None:
    ctx = make_ctx(
        tmp_path, sources={"fake": _fackel_source()}, notifier=FakeNotifier(fail=True)
    )
    run_profile(ctx, make_profile())
    working = FakeNotifier()

    second = run_profile(dataclasses.replace(ctx, notifier=working), make_profile())

    assert second.found == [FACKEL]
    assert len(working.sent) == 1


def test_missing_notifier_does_not_mark_notified(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = make_ctx(tmp_path, sources={"fake": _fackel_source()}, notifier=None)

    run_profile(ctx, make_profile())
    second = run_profile(ctx, make_profile())

    assert second.found == [FACKEL]
    assert "no notifier configured" in caplog.text


def test_download_success_sends_no_mail_by_default(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    downloader = FakeDownloader(tmp_path)
    ctx = make_ctx(
        tmp_path,
        sources={"fake": _fackel_source()},
        notifier=notifier,
        downloader=downloader,
    )
    profile = make_profile(action="download")

    first = run_profile(ctx, profile)
    second = run_profile(ctx, profile)

    assert first.downloaded == [(FACKEL, tmp_path / "filme" / "f1.mp4")]
    assert first.found == []
    assert second.downloaded == []
    assert downloader.calls == [FACKEL]
    assert notifier.sent == []


def test_download_failure_retries_until_limit(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    downloader = FakeDownloader(tmp_path, fail=True)
    ctx = make_ctx(
        tmp_path,
        sources={"fake": _fackel_source()},
        notifier=notifier,
        downloader=downloader,
        max_retries=2,
    )
    profile = make_profile(action="download")

    reports = [run_profile(ctx, profile) for _ in range(3)]

    assert [(f.attempts, f.final) for f in reports[0].failed] == [(1, False)]
    assert [(f.attempts, f.final) for f in reports[1].failed] == [(2, True)]
    assert reports[2].failed == []
    assert len(downloader.calls) == 2
    assert len(notifier.sent) == 2


@pytest.mark.parametrize(
    ("notify", "fail", "mails"),
    [
        ("never", True, 0),
        ("errors", False, 0),
        ("errors", True, 1),
        ("always", False, 1),
        ("always", True, 1),
    ],
)
def test_notify_setting_for_downloads(
    tmp_path: Path, notify: str, fail: bool, mails: int
) -> None:
    notifier = FakeNotifier()
    ctx = make_ctx(
        tmp_path,
        sources={"fake": _fackel_source()},
        notifier=notifier,
        downloader=FakeDownloader(tmp_path, fail=fail),
    )

    run_profile(ctx, make_profile(action="download", notify=notify))

    assert len(notifier.sent) == mails


def test_both_notifies_and_downloads(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, sources={"fake": _fackel_source()}, notifier=notifier)
    profile = make_profile(action="both", notify="never")

    first = run_profile(ctx, profile)
    second = run_profile(ctx, profile)

    assert first.found == [FACKEL]
    assert [hit for hit, _ in first.downloaded] == [FACKEL]
    assert len(notifier.sent) == 1
    assert (second.found, second.downloaded) == ([], [])


def test_source_error_skips_only_that_source(tmp_path: Path) -> None:
    broken = FakeSource(name="broken", error=SourceError("broken: HTTP 503"))
    ctx = make_ctx(
        tmp_path,
        sources={"broken": broken, "fake": _fackel_source()},
        notifier=FakeNotifier(),
    )
    profile = make_profile(
        sources=["broken", "fake"], terms=("Tatort Fackel", "Unter Freunden")
    )

    report = run_profile(ctx, profile)

    assert report.errors == ["broken: HTTP 503"]
    assert report.found == [FACKEL]
    assert broken.queries == ["Tatort Fackel"]


def test_same_film_from_two_terms_triggers_once(tmp_path: Path) -> None:
    # Review focus 4: overlapping terms must not duplicate actions.
    notifier = FakeNotifier()
    source = FakeSource(results={"Tatort Fackel": [FACKEL], "Fackel": [FACKEL]})
    ctx = make_ctx(tmp_path, sources={"fake": source}, notifier=notifier)

    report = run_profile(ctx, make_profile(terms=("Tatort Fackel", "Fackel")))

    assert report.found == [FACKEL]
    assert len(notifier.sent) == 1


def test_same_film_on_two_channels_picks_best(tmp_path: Path) -> None:
    orf = make_hit(
        source_id="o1",
        channel="ORF",
        title="Tatort: Unter Freunden",
        duration=5170,
        is_hls=True,
        video_url="https://orf.example/x.m3u8",
    )
    source = FakeSource(results={"Tatort Unter Freunden": [orf, FREUNDE]})
    ctx = make_ctx(tmp_path, sources={"fake": source}, notifier=FakeNotifier())

    report = run_profile(ctx, make_profile(terms=("Tatort Unter Freunden",)))

    assert report.found == [FREUNDE]


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    downloader = FakeDownloader(tmp_path)
    ctx = make_ctx(
        tmp_path,
        sources={"fake": _fackel_source()},
        notifier=notifier,
        downloader=downloader,
        dry_run=True,
    )

    report = run_profile(ctx, make_profile(action="both"))

    assert report.found == [FACKEL]
    assert report.planned == [FACKEL]
    assert downloader.calls == []
    assert notifier.sent == []
    assert ctx.store.find("test", FACKEL) is None


def test_unknown_source_raises_config_error(tmp_path: Path) -> None:
    def resolver(name: str) -> FakeSource:
        raise ConfigError(f"unknown source {name!r}")

    ctx = make_ctx(tmp_path, sources=resolver)

    with pytest.raises(ConfigError, match="unknown source"):
        run_profile(ctx, make_profile())


def test_empty_title_list_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = make_ctx(tmp_path, sources={"fake": _fackel_source()})

    with caplog.at_level(logging.WARNING):
        report = run_profile(ctx, make_profile(terms=()))

    assert report.found == []
    assert "empty" in caplog.text


@pytest.mark.parametrize(
    ("action", "notify", "fields", "expected"),
    [
        ("info", "errors", {}, False),
        ("info", "never", {"found": [FACKEL]}, True),
        ("info", "always", {"errors": ["x"]}, False),
        ("download", "never", {"errors": ["x"]}, False),
        ("download", "errors", {"errors": ["x"]}, True),
        ("download", "always", {}, False),
    ],
)
def test_should_notify(
    action: str, notify: str, fields: dict[str, list[object]], expected: bool
) -> None:
    report = Report(profile="test", **fields)

    profile = make_profile(action=action, notify=notify).profile

    assert should_notify(report, profile) is expected


def test_open_context_wires_components_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[FakeSource] = []

    def fake_get_source(name: str) -> FakeSource:
        created.append(FakeSource(name=name))
        return created[-1]

    monkeypatch.setattr("real_fast_cinema.runner.get_source", fake_get_source)
    config = GlobalConfig.model_validate(
        {
            "data_dir": tmp_path / "data",
            "downloads_root": tmp_path / "media",
            "smtp": {"host": "smtp.example.org", "from": "bot@example.org"},
        }
    )

    with open_context(config) as ctx:
        assert ctx.sources("mediathekviewweb") is ctx.sources("mediathekviewweb")
        assert isinstance(ctx.notifier, EmailNotifier)
        assert ctx.dry_run is False

    assert len(created) == 1
    assert created[0].closed is True
    assert (tmp_path / "data" / "state.db").exists()


def test_open_context_dry_run_creates_no_state(tmp_path: Path) -> None:
    config = GlobalConfig.model_validate(
        {"data_dir": tmp_path / "data", "downloads_root": tmp_path / "media"}
    )

    with open_context(config, dry_run=True) as ctx:
        assert ctx.notifier is None
        assert ctx.dry_run is True

    assert not (tmp_path / "data").exists()


def test_fakes_module_exposes_now() -> None:
    assert fakes.NOW.tzinfo is not None
