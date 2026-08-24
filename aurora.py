"""Aurora desktop application entry point."""

import logging
import sys

from util.logging_config import configure_logging


def select_ui_runner(arguments: list[str] | None = None):
    """Prefer the Qt interface and retain Tk as an explicit compatibility UI."""
    options = sys.argv[1:] if arguments is None else arguments
    if "--tk" not in options:
        try:
            from gui.qt_application import run

            return run
        except ImportError:
            pass
    from gui.application import run

    return run


if __name__ == "__main__":
    configure_logging()
    logger = logging.getLogger("aurora")
    logger.info("Aurora starting")
    try:
        select_ui_runner()()
    finally:
        logger.info("Aurora stopped")
