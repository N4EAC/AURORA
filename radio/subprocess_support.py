"""Platform-specific subprocess options for background radio services."""

from __future__ import annotations

import platform
import subprocess


def hidden_process_kwargs(system: str | None = None) -> dict[str, int]:
    """Return flags that prevent a child console window on Windows."""
    if (system or platform.system()) != "Windows":
        return {}
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    }
