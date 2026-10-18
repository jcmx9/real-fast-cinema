"""Daemon scheduling: decides which profiles are due and runs them."""

import logging
import threading
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from pathlib import Path

from real_fast_cinema.config import GlobalConfig
from real_fast_cinema.exceptions import ConfigError, RfCinemaError
from real_fast_cinema.loader import LoadedProfile, load_global, load_profiles
from real_fast_cinema.runner import RunContext, run_profile
from real_fast_cinema.store import Store

logger = logging.getLogger(__name__)

OpenContext = Callable[[GlobalConfig], AbstractContextManager[RunContext]]


def _interval(loaded: LoadedProfile, default_every: timedelta) -> timedelta:
    return loaded.profile.every or default_every


def due_profiles(
    profiles: Sequence[LoadedProfile],
    store: Store,
    default_every: timedelta,
    now: datetime,
) -> list[LoadedProfile]:
    """Profiles that never ran or whose interval has elapsed."""
    due: list[LoadedProfile] = []
    for loaded in profiles:
        last = store.last_run(loaded.profile.name)
        if last is None or now - last >= _interval(loaded, default_every):
            due.append(loaded)
    return due


def seconds_until_next(
    profiles: Sequence[LoadedProfile],
    store: Store,
    default_every: timedelta,
    now: datetime,
) -> float:
    """Seconds until the next profile is due (``inf`` without profiles)."""
    waits: list[float] = []
    for loaded in profiles:
        last = store.last_run(loaded.profile.name)
        if last is None:
            return 0.0
        waits.append((last + _interval(loaded, default_every) - now).total_seconds())
    return max(0.0, min(waits, default=float("inf")))


def tick(ctx: RunContext, profiles: Sequence[LoadedProfile]) -> float:
    """Runs all due profiles once; returns seconds until the next is due."""
    now = ctx.now()
    default_every = ctx.config.defaults.every
    for loaded in due_profiles(profiles, ctx.store, default_every, now):
        name = loaded.profile.name
        try:
            run_profile(ctx, loaded)
        except RfCinemaError as exc:
            logger.error("profile %s failed: %s", name, exc)
        except Exception:
            logger.exception("profile %s crashed", name)
        ctx.store.set_last_run(name, now)
    return seconds_until_next(profiles, ctx.store, default_every, ctx.now())


def run_daemon(
    config_dir: Path,
    open_ctx: OpenContext,
    stop: threading.Event,
    max_sleep: float = 300.0,
) -> None:
    """Re-reads the configuration and runs due profiles until ``stop`` is set."""
    logger.info("daemon started (config: %s)", config_dir)
    while not stop.is_set():
        delay = max_sleep
        try:
            config = load_global(config_dir)
            profiles, errors = load_profiles(config_dir)
            for message in errors:
                logger.error("%s", message)
            with open_ctx(config) as ctx:
                delay = min(max_sleep, tick(ctx, profiles))
        except ConfigError as exc:
            logger.error("%s", exc)
        except Exception:
            logger.exception("daemon iteration failed")
        logger.debug("sleeping %.0f s", delay)
        stop.wait(delay)
    logger.info("daemon stopped")
