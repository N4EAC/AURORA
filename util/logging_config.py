"""Logging configuration for Aurora."""

import logging
from logging.handlers import RotatingFileHandler

from config import AppSettings, SETTINGS


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(settings: AppSettings = SETTINGS) -> logging.Logger:
    """Configure console and rotating-file logging for Aurora."""
    logger = logging.getLogger("aurora")
    if logger.handlers:
        return logger

    logger.setLevel(settings.log_level)
    logger.propagate = False
    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    settings.log_directory.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        settings.log_directory / settings.log_filename,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
