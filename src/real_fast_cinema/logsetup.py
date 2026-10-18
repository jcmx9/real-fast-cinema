"""Logging setup for the verbosity levels of the CLI.

Verbosity: 0 silent (file only), 1 standard, 2 verbose, 3 debug.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

VERBOSE = 15
logging.addLevelName(VERBOSE, "VERBOSE")

LOG_FILE = "rf-cinema.log"
_MARKER = "_rf_cinema"
_CONSOLE_LEVELS = {1: logging.INFO, 2: VERBOSE}


def teardown_logging() -> None:
    """Removes all handlers installed by ``setup_logging``."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _MARKER, False):
            root.removeHandler(handler)
            handler.close()


def setup_logging(verbosity: int, log_dir: Path | None) -> None:
    """Installs console and file handlers for ``verbosity``."""
    teardown_logging()
    root = logging.getLogger()
    levels: list[int] = []
    if verbosity > 0:
        console = logging.StreamHandler()
        console.setLevel(_CONSOLE_LEVELS.get(verbosity, logging.DEBUG))
        console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        handlers: list[logging.Handler] = [console]
    else:
        handlers = []
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG if verbosity >= 3 else VERBOSE)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        handlers.append(file_handler)
    for handler in handlers:
        setattr(handler, _MARKER, True)
        root.addHandler(handler)
        levels.append(handler.level)
    root.setLevel(min(levels, default=logging.WARNING))
    logging.getLogger("httpx").setLevel(
        logging.DEBUG if verbosity >= 3 else logging.WARNING
    )
