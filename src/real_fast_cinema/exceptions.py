"""Project-specific exceptions."""


class RfCinemaError(Exception):
    """Base class for all expected errors of rf-cinema."""


class ConfigError(RfCinemaError):
    """Invalid or missing configuration, profile or title list."""


class SourceError(RfCinemaError):
    """A source could not be queried."""


class DownloadError(RfCinemaError):
    """A download failed."""


class NotifyError(RfCinemaError):
    """A notification could not be delivered."""
