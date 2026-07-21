"""Aurora desktop application entry point."""

import logging

from gui.application import run
from util.logging_config import configure_logging


if __name__ == "__main__":
    configure_logging()
    logger = logging.getLogger("aurora")
    logger.info("Aurora starting")
    try:
        run()
    finally:
        logger.info("Aurora stopped")
