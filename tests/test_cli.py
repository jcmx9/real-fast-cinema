from pathlib import Path

import pytest
from typer.testing import CliRunner

from real_fast_cinema import __version__, cli
from real_fast_cinema.cli import app
from real_fast_cinema.exceptions import SourceError
from tests.fakes import FakeNotifier, FakeSource, make_hit

runner = CliRunner()


def test_version_flag_prints_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"rf-cinema {__version__}"


def test_no_arguments_shows_help_with_version() -> None:
    result = runner.invoke(app, [])

    assert "Usage" in result.output
    assert __version__ in result.output


MARPLE = make_hit(source_id="m1", topic="Miss Marple", title="16 Uhr 50 ab Paddington")


@pytest.fixture
def fake_source(monkeypatch: pytest.MonkeyPatch) -> FakeSource:
    source = FakeSource(name="mediathekviewweb", results={"Miss Marple": [MARPLE]})
    monkeypatch.setattr("real_fast_cinema.runner.get_source", lambda name: source)
    return source


@pytest.fixture
def fake_notifier(monkeypatch: pytest.MonkeyPatch) -> FakeNotifier:
    notifier = FakeNotifier()
    monkeypatch.setattr(
        "real_fast_cinema.runner.EmailNotifier", lambda smtp, password: notifier
    )
    return notifier


def test_list_sources() -> None:
    result = runner.invoke(app, ["list-sources"])

    assert result.exit_code == 0
    assert result.output.strip() == "mediathekviewweb"


def test_check_shows_dry_run_and_writes_no_state(
    config_dir: Path, fake_source: FakeSource, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["check", "-c", str(config_dir), "-Q"])

    assert result.exit_code == 0, result.output
    assert "[krimis]" in result.output
    assert "notify" in result.output
    assert "mail:     would be sent" in result.output
    assert "16 Uhr 50 ab Paddington" in result.output
    assert not (tmp_path / "data").exists()


def test_check_unknown_profile(config_dir: Path) -> None:
    result = runner.invoke(app, ["check", "-c", str(config_dir), "-p", "nope"])

    assert result.exit_code == 1
    assert "Error: unknown profile 'nope'" in result.output


def test_check_reports_broken_profile_without_traceback(config_dir: Path) -> None:
    (config_dir / "profiles" / "broken.yaml").write_text("name: [", encoding="utf-8")

    result = runner.invoke(app, ["check", "-c", str(config_dir)])

    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "broken.yaml" in result.output
    assert "Traceback" not in result.output


def test_check_rejects_unknown_source(config_dir: Path) -> None:
    (config_dir / "profiles" / "krimis.yaml").write_text(
        "name: krimis\nsources: [nope]\ntitles: krimis.txt\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["check", "-c", str(config_dir)])

    assert result.exit_code == 1
    assert "unknown source 'nope'" in result.output


def test_check_requires_smtp_for_notifications(config_dir: Path) -> None:
    (config_dir / "config.yaml").write_text(
        "data_dir: data\ndownloads_root: media\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["check", "-c", str(config_dir)])

    assert result.exit_code == 1
    assert "smtp" in result.output


def test_check_missing_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", "-c", str(tmp_path)])

    assert result.exit_code == 1
    assert "configuration file not found" in result.output


def test_run_notifies_and_records_state(
    config_dir: Path,
    fake_source: FakeSource,
    fake_notifier: FakeNotifier,
    tmp_path: Path,
) -> None:
    first = runner.invoke(app, ["run", "-c", str(config_dir), "-Q"])
    second = runner.invoke(app, ["run", "-c", str(config_dir), "-Q"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert len(fake_notifier.sent) == 1
    assert (tmp_path / "data" / "state.db").exists()
    assert (tmp_path / "data" / "rf-cinema.log").exists()


def test_run_partial_failure_exit_code(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_notifier: FakeNotifier,
) -> None:
    broken = FakeSource(name="mediathekviewweb", error=SourceError("down"))
    monkeypatch.setattr("real_fast_cinema.runner.get_source", lambda name: broken)

    result = runner.invoke(app, ["run", "-c", str(config_dir), "-Q"])

    assert result.exit_code == 2


def test_daemon_starts_loop(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(
        cli, "run_daemon", lambda path, open_ctx, stop: calls.append(path)
    )
    monkeypatch.setattr(cli.signal, "signal", lambda signum, handler: None)

    result = runner.invoke(app, ["daemon", "-c", str(config_dir), "-Q"])

    assert result.exit_code == 0, result.output
    assert calls == [config_dir]


def test_daemon_missing_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["daemon", "-c", str(tmp_path)])

    assert result.exit_code == 1
    assert "Error:" in result.output


@pytest.mark.parametrize(
    ("flags", "level"),
    [
        ((False, False, False), 1),
        ((True, True, True), 0),
        ((False, True, False), 2),
        ((False, True, True), 3),
    ],
)
def test_verbosity(flags: tuple[bool, bool, bool], level: int) -> None:
    assert cli.verbosity(*flags) == level
