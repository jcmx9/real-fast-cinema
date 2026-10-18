"""Source plugin protocol."""

from typing import Protocol

from real_fast_cinema.models import Hit


class Source(Protocol):
    """A searchable media service."""

    name: str

    def search(self, term: str) -> list[Hit]:
        """Returns all hits the service reports for ``term``.

        Raises:
            SourceError: If the service cannot be queried.
        """
        ...

    def close(self) -> None:
        """Releases network resources."""
        ...
