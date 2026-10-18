"""Notifier plugin protocol."""

from collections.abc import Sequence
from typing import Protocol

from real_fast_cinema.models import Report


class Notifier(Protocol):
    """A channel that delivers run reports."""

    def send(self, report: Report, recipients: Sequence[str]) -> None:
        """Delivers ``report``.

        Raises:
            NotifyError: If delivery fails.
        """
        ...
