import pytest

from real_fast_cinema.exceptions import (
    ConfigError,
    DownloadError,
    NotifyError,
    RfCinemaError,
    SourceError,
)


@pytest.mark.parametrize(
    "error_type",
    [ConfigError, SourceError, DownloadError, NotifyError],
)
def test_specific_errors_derive_from_base_error(error_type: type[Exception]) -> None:
    assert issubclass(error_type, RfCinemaError)
    assert str(error_type("boom")) == "boom"
