import logging
from pathlib import Path

from real_fast_cinema.logsetup import LOG_FILE, VERBOSE, setup_logging


def _own_handlers() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if getattr(h, "_rf_cinema", False)]


def _console_levels() -> list[int]:
    return [h.level for h in _own_handlers() if not isinstance(h, logging.FileHandler)]


def test_silent_logs_only_to_file(tmp_path: Path) -> None:
    setup_logging(0, tmp_path)
    logging.getLogger("real_fast_cinema.test").info("hello file")
    for handler in _own_handlers():
        handler.flush()

    assert _console_levels() == []
    assert "hello file" in (tmp_path / LOG_FILE).read_text(encoding="utf-8")


def test_levels_per_verbosity(tmp_path: Path) -> None:
    setup_logging(1, None)
    assert _console_levels() == [logging.INFO]

    setup_logging(2, None)
    assert _console_levels() == [VERBOSE]

    setup_logging(3, tmp_path)
    assert _console_levels() == [logging.DEBUG]
    file_levels = [
        h.level for h in _own_handlers() if isinstance(h, logging.FileHandler)
    ]
    assert file_levels == [logging.DEBUG]
    assert logging.getLogger().level == logging.DEBUG


def test_setup_replaces_previous_handlers(tmp_path: Path) -> None:
    setup_logging(1, tmp_path)
    setup_logging(1, tmp_path)

    assert len(_own_handlers()) == 2
