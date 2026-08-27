"""Create native-build output roots and validate required source inputs."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEMANTIC_VERSION = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def validate(platform_name: str, version: str) -> None:
    """Prepare stable output roots and reject incomplete source checkouts."""
    if sys.version_info < (3, 10):
        raise RuntimeError("Aurora native builds require Python 3.10 or newer")
    if not SEMANTIC_VERSION.fullmatch(version):
        raise RuntimeError(f"AURORA_VERSION is not semantic: {version!r}")
    required = [
        "aurora.py",
        "requirements.txt",
        "requirements-build.txt",
        "packaging/aurora.spec",
        "assets/aurora-icon.png",
    ]
    platform_key = platform_name.lower()
    if platform_key == "windows":
        required.extend(("assets/aurora.ico", "packaging/windows/Aurora.iss"))
    elif platform_key == "macos":
        required.append("assets/aurora.icns")
    elif platform_key not in {"ubuntu", "fedora"}:
        raise RuntimeError(f"Unsupported Aurora build platform: {platform_name}")
    missing = [name for name in required if not (PROJECT_ROOT / name).is_file()]
    if missing:
        raise RuntimeError("Missing build input(s): " + ", ".join(missing))
    (PROJECT_ROOT / "build").mkdir(exist_ok=True)
    (PROJECT_ROOT / "dist").mkdir(exist_ok=True)
    (PROJECT_ROOT / "dist" / "installer").mkdir(parents=True, exist_ok=True)
    print(
        f"Aurora {platform_name} preflight complete: "
        f"{PROJECT_ROOT / 'dist'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("platform")
    parser.add_argument("version")
    arguments = parser.parse_args()
    validate(arguments.platform, arguments.version)


if __name__ == "__main__":
    main()
