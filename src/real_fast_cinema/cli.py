"""Command line interface."""

import logging
import shutil
import signal
import threading
from pathlib import Path
from types import FrameType
from typing import Annotated, NoReturn

import typer

from real_fast_cinema import __version__
from real_fast_cinema.config import GlobalConfig
from real_fast_cinema.exceptions import ConfigError, RfCinemaError
from real_fast_cinema.loader import LoadedProfile, load_global, load_profiles
from real_fast_cinema.logsetup import setup_logging
from real_fast_cinema.runner import open_context, run_profile, should_notify
from real_fast_cinema.scheduler import run_daemon
from real_fast_cinema.sources import available_sources

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="rf-cinema",
    help=f"Searches media libraries for films from title lists (v{__version__})",
    no_args_is_help=True,
)

ConfigDir = Annotated[
    Path,
    typer.Option(
        "--config",
        "-c",
        envvar="RF_CINEMA_CONFIG",
        file_okay=False,
        help="Configuration directory.",
    ),
]
ProfileName = Annotated[
    str | None, typer.Option("--profile", "-p", help="Only this profile.")
]
Silent = Annotated[
    bool, typer.Option("--silent", "-Q", help="No console output (log file only).")
]
Verbose = Annotated[bool, typer.Option("--verbose", "-v", help="Extended output.")]
Debug = Annotated[bool, typer.Option("--debug", "-vv", help="Debug output.")]


FFMPEG_HINT = "ffmpeg not found - HLS downloads will fail"


def _ffmpeg_missing() -> bool:
    return shutil.which("ffmpeg") is None


def _warn_missing_ffmpeg() -> None:
    if _ffmpeg_missing():
        logger.warning(FFMPEG_HINT)


def verbosity(silent: bool, verbose: bool, debug: bool) -> int:
    """Maps the verbosity flags to 0 (silent) .. 3 (debug)."""
    return 0 if silent else (3 if debug else (2 if verbose else 1))


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _load(
    config_dir: Path, profile_name: str | None
) -> tuple[GlobalConfig, list[LoadedProfile]]:
    try:
        config = load_global(config_dir)
        profiles, errors = load_profiles(config_dir)
    except ConfigError as exc:
        _fail(str(exc))
    if errors:
        _fail("\n".join(errors))
    if profile_name is not None:
        profiles = [p for p in profiles if p.profile.name == profile_name]
        if not profiles:
            _fail(f"unknown profile {profile_name!r}")
    known = set(available_sources())
    for loaded in profiles:
        for name in loaded.profile.sources:
            if name not in known:
                _fail(
                    f"{loaded.path}: unknown source {name!r} "
                    f"(available: {', '.join(sorted(known))})"
                )
    return config, profiles


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


@app.command()
def run(
    config_dir: ConfigDir = Path("config"),
    profile: ProfileName = None,
    silent: Silent = False,
    verbose: Verbose = False,
    debug: Debug = False,
) -> None:
    """Run all (or one) profiles once and exit (exit code 2 on partial failure)."""
    config, profiles = _load(config_dir, profile)
    setup_logging(verbosity(silent, verbose, debug), config.data_dir)
    _warn_missing_ffmpeg()
    partial = False
    try:
        with open_context(config) as ctx:
            for loaded in profiles:
                report = run_profile(ctx, loaded)
                ctx.store.set_last_run(loaded.profile.name, ctx.now())
                partial = partial or bool(report.failed or report.errors)
    except RfCinemaError as exc:
        _fail(str(exc))
    if partial:
        raise typer.Exit(2)


@app.command()
def daemon(
    config_dir: ConfigDir = Path("config"),
    silent: Silent = False,
    verbose: Verbose = False,
    debug: Debug = False,
) -> None:
    """Run continuously and execute profiles when they are due."""
    try:
        config = load_global(config_dir)
    except ConfigError as exc:
        _fail(str(exc))
    setup_logging(verbosity(silent, verbose, debug), config.data_dir)
    _warn_missing_ffmpeg()
    stop = threading.Event()

    def _stop(signum: int, frame: FrameType | None) -> None:
        logger.info("received signal %d, stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    run_daemon(config_dir, open_context, stop)


@app.command()
def check(
    config_dir: ConfigDir = Path("config"),
    profile: ProfileName = None,
    silent: Silent = False,
    verbose: Verbose = False,
    debug: Debug = False,
) -> None:
    """Validate the configuration and show what a run would do (dry run)."""
    config, profiles = _load(config_dir, profile)
    setup_logging(verbosity(silent, verbose, debug), None)
    needs_mail = [
        p.profile.name
        for p in profiles
        if p.profile.action != "download" or p.profile.notify != "never"
    ]
    if needs_mail and config.smtp is None:
        _fail(f"profiles {needs_mail} send mail but config.yaml has no smtp section")
    if _ffmpeg_missing():
        typer.echo(f"Warning: {FFMPEG_HINT}", err=True)
    try:
        with open_context(config, dry_run=True) as ctx:
            for loaded in profiles:
                report = run_profile(ctx, loaded)
                p = loaded.profile
                typer.echo(
                    f"[{p.name}] {len(loaded.terms)} terms, "
                    f"sources: {', '.join(p.sources)}, action: {p.action}"
                )
                for hit in report.found:
                    typer.echo(f"  notify:   {hit.topic} - {hit.title} ({hit.channel})")
                for hit in report.planned:
                    typer.echo(f"  download: {hit.topic} - {hit.title} ({hit.channel})")
                for error in report.errors:
                    typer.echo(f"  error:    {error}")
                if should_notify(report, p):
                    typer.echo("  mail:     would be sent")
    except RfCinemaError as exc:
        _fail(str(exc))


@app.command("list-sources")
def list_sources() -> None:
    """List the available sources."""
    for name in available_sources():
        typer.echo(name)
