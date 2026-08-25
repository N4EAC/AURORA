"""Validate release inputs and create metadata shared by native builds."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEMANTIC_VERSION = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def prepare(version: str) -> Path:
    """Validate *version* and write the metadata consumed by PyInstaller."""
    if not SEMANTIC_VERSION.fullmatch(version):
        raise ValueError(f"AURORA_VERSION is not a semantic version: {version!r}")
    destination = PROJECT_ROOT / "build" / "generated" / "aurora-version.txt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(f"{version}\n", encoding="utf-8")
    print(f"Prepared Aurora {version} build metadata: {destination}")
    return destination


def main() -> None:
    """Prepare metadata for the requested application version."""
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    arguments = parser.parse_args()
    prepare(arguments.version)


if __name__ == "__main__":
    main()
