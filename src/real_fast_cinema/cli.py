"""Command line interface."""

import typer

from real_fast_cinema import __version__

app = typer.Typer(
    name="rf-cinema",
    help=f"Searches media libraries for films from title lists (v{__version__})",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"rf-cinema {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """rf-cinema command line."""
