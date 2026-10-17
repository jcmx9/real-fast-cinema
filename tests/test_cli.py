from typer.testing import CliRunner

from real_fast_cinema import __version__
from real_fast_cinema.cli import app

runner = CliRunner()


def test_version_flag_prints_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"rf-cinema {__version__}"


def test_no_arguments_shows_help_with_version() -> None:
    result = runner.invoke(app, [])

    assert "Usage" in result.output
    assert __version__ in result.output
