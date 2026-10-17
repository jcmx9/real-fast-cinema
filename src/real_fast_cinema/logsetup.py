"""Logging setup for the verbosity levels of the CLI."""

import logging

VERBOSE = 15
logging.addLevelName(VERBOSE, "VERBOSE")
