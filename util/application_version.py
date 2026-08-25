"""Resolve Aurora's version in source and frozen application layouts."""

from __future__ import annotations

from pathlib import Path
import sys


DEVELOPMENT_VERSION = "0.1.0-dev"


def application_version() -> str:
    """Return bundled release metadata or the source development version."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is None:
        return DEVELOPMENT_VERSION
    metadata = Path(bundle_root) / "aurora-version.txt"
    try:
        version = metadata.read_text(encoding="utf-8").strip()
    except OSError:
        return DEVELOPMENT_VERSION
    return version or DEVELOPMENT_VERSION


APPLICATION_VERSION = application_version()
