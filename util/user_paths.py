"""Resolve writable Aurora runtime directories across supported platforms."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import platform
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _runtime_context(
    *,
    frozen: bool | None,
    system: str | None,
    environment: Mapping[str, str] | None,
    home: Path | None,
) -> tuple[bool, str, Mapping[str, str], Path]:
    return (
        bool(getattr(sys, "frozen", False)) if frozen is None else frozen,
        platform.system() if system is None else system,
        os.environ if environment is None else environment,
        Path.home() if home is None else home,
    )


def application_log_directory(
    *,
    frozen: bool | None = None,
    system: str | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return Aurora's writable directory for application and session logs."""
    frozen, system, environment, home = _runtime_context(
        frozen=frozen, system=system, environment=environment, home=home
    )
    if not frozen:
        return PROJECT_ROOT / "logs"
    if system == "Darwin":
        return home / "Library" / "Logs" / "Aurora"
    if system == "Windows":
        local = Path(environment.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return local / "Aurora" / "logs"
    state = Path(environment.get("XDG_STATE_HOME", home / ".local" / "state"))
    return state / "Aurora" / "logs"


def application_data_directory(
    *,
    frozen: bool | None = None,
    system: str | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return Aurora's writable directory for persistent application data."""
    frozen, system, environment, home = _runtime_context(
        frozen=frozen, system=system, environment=environment, home=home
    )
    if not frozen:
        return PROJECT_ROOT / "data"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "Aurora"
    if system == "Windows":
        local = Path(environment.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return local / "Aurora"
    data = Path(environment.get("XDG_DATA_HOME", home / ".local" / "share"))
    return data / "Aurora"
