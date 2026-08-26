"""Aurora desktop application entry point."""

import importlib
import logging
import sys

from util.logging_config import configure_logging


def select_ui_runner(arguments: list[str] | None = None):
    """Prefer Qt and expose Tk only from an unfrozen source checkout."""
    options = sys.argv[1:] if arguments is None else arguments
    frozen = bool(getattr(sys, "frozen", False))
    if "--tk" in options:
        if frozen:
            raise RuntimeError("The packaged Aurora application includes the Qt UI only")
        return importlib.import_module("gui.application").run
    try:
        return importlib.import_module("gui.qt_application").run
    except ImportError:
        if frozen:
            raise
        return importlib.import_module("gui.application").run


if __name__ == "__main__":
    configure_logging()
    logger = logging.getLogger("aurora")
    logger.info("Aurora starting")
    try:
        select_ui_runner()()
    finally:
        logger.info("Aurora stopped")
