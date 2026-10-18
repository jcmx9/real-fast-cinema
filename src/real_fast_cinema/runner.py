"""Executes one profile run and wires the components together."""

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from real_fast_cinema.config import DownloadOpts, GlobalConfig, Profile
from real_fast_cinema.download import Downloader
from real_fast_cinema.exceptions import (
    ConfigError,
    DownloadError,
    NotifyError,
    SourceError,
)
from real_fast_cinema.loader import LoadedProfile
from real_fast_cinema.logsetup import VERBOSE
from real_fast_cinema.matching import best_hit, group_hits, select
from real_fast_cinema.models import Failure, Hit, Report
from real_fast_cinema.notifiers.base import Notifier
from real_fast_cinema.notifiers.email import EmailNotifier
from real_fast_cinema.sources import get_source
from real_fast_cinema.sources.base import Source
from real_fast_cinema.store import Store

logger = logging.getLogger(__name__)

PASSWORD_ENV = "RF_CINEMA_SMTP_PASSWORD"
STATE_DB = "state.db"


class Downloading(Protocol):
    """Anything that can download a hit."""

    def download(self, hit: Hit, opts: DownloadOpts) -> Path:
        """Downloads ``hit`` and returns the file path."""
        ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RunContext:
    """Everything a profile run needs."""

    config: GlobalConfig
    store: Store
    sources: Callable[[str], Source]
    downloader: Downloading
    notifier: Notifier | None
    dry_run: bool = False
    now: Callable[[], datetime] = field(default=_utcnow)


def run_profile(ctx: RunContext, loaded: LoadedProfile) -> Report:
    """Searches, filters, deduplicates and acts for one profile.

    Raises:
        ConfigError: If a source of the profile is unknown.
    """
    profile = loaded.profile
    report = Report(profile=profile.name)
    if not loaded.terms:
        logger.warning("%s: title list %s is empty", profile.name, profile.titles)
    hits = _collect(ctx, loaded, report)
    for group in group_hits(hits):
        _handle(ctx, profile, best_hit(group), report)
    if not ctx.dry_run:
        _notify(ctx, profile, report)
    logger.info("%s: %s", profile.name, report.summary())
    return report


def _collect(ctx: RunContext, loaded: LoadedProfile, report: Report) -> list[Hit]:
    profile = loaded.profile
    sources = [ctx.sources(name) for name in profile.sources]
    hits: list[Hit] = []
    for source in sources:
        for term in loaded.terms:
            try:
                found = source.search(term)
            except SourceError as exc:
                logger.warning("%s: %s (skipping source this run)", profile.name, exc)
                report.errors.append(str(exc))
                break
            selected = [h for h in found if select(h, term, profile.filters)]
            logger.log(
                VERBOSE,
                "%s: %r on %s: %d of %d hits selected",
                profile.name,
                term,
                source.name,
                len(selected),
                len(found),
            )
            hits.extend(selected)
    return hits


def _handle(ctx: RunContext, profile: Profile, hit: Hit, report: Report) -> None:
    record = ctx.store.find(profile.name, hit)
    max_retries = ctx.config.defaults.max_retries
    attempts = record.attempts if record is not None else 0
    need_info = profile.action in ("info", "both") and not (
        record is not None and record.notified
    )
    need_download = (
        profile.action in ("download", "both")
        and not (record is not None and record.downloaded)
        and attempts < max_retries
    )
    if not (need_info or need_download):
        logger.log(VERBOSE, "%s: already handled: %s", profile.name, hit.title)
        return
    if need_info:
        report.found.append(hit)
    if not need_download:
        return
    if ctx.dry_run:
        report.planned.append(hit)
        return
    if profile.download is None:  # guaranteed by Profile validation
        raise ConfigError(f"profile {profile.name}: missing download section")
    try:
        path = ctx.downloader.download(hit, profile.download)
    except DownloadError as exc:
        attempts = ctx.store.mark_failed(profile.name, hit, str(exc))
        final = attempts >= max_retries
        logger.error(
            "%s: download of %s failed (attempt %d/%d): %s",
            profile.name,
            hit.title,
            attempts,
            max_retries,
            exc,
        )
        report.failed.append(
            Failure(hit=hit, error=str(exc), attempts=attempts, final=final)
        )
    else:
        ctx.store.mark_downloaded(profile.name, hit, path)
        report.downloaded.append((hit, path))


def should_notify(report: Report, profile: Profile) -> bool:
    """Decides whether ``report`` must be sent for ``profile``."""
    if report.found:
        return True
    if profile.action == "info":
        return False
    if profile.notify == "always":
        return bool(report.downloaded or report.failed or report.errors)
    if profile.notify == "errors":
        return bool(report.failed or report.errors)
    return False


def _notify(ctx: RunContext, profile: Profile, report: Report) -> None:
    if not should_notify(report, profile):
        return
    if ctx.notifier is None:
        logger.warning(
            "%s: notification needed but no notifier configured", profile.name
        )
        return
    recipients = profile.mail_to or ctx.config.mail_to
    try:
        ctx.notifier.send(report, recipients)
    except NotifyError as exc:
        logger.error("%s: %s (will retry next run)", profile.name, exc)
        return
    for hit in report.found:
        ctx.store.mark_notified(profile.name, hit)


@contextmanager
def open_context(
    config: GlobalConfig, *, dry_run: bool = False
) -> Iterator[RunContext]:
    """Creates store, sources, downloader and notifier; closes them afterwards.

    In dry-run mode no state database is created.
    """
    db_path = config.data_dir / STATE_DB
    store = Store(None if dry_run and not db_path.exists() else db_path)
    sources: dict[str, Source] = {}

    def resolve(name: str) -> Source:
        if name not in sources:
            sources[name] = get_source(name)
        return sources[name]

    notifier: Notifier | None = None
    if config.smtp is not None:
        notifier = EmailNotifier(config.smtp, os.environ.get(PASSWORD_ENV))
    downloader = Downloader(config.downloads_root)
    try:
        yield RunContext(
            config=config,
            store=store,
            sources=resolve,
            downloader=downloader,
            notifier=notifier,
            dry_run=dry_run,
        )
    finally:
        for source in sources.values():
            source.close()
        downloader.close()
        store.close()
