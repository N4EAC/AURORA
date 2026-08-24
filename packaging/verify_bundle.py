"""Perform platform-independent structural checks on an Aurora bundle."""

from __future__ import annotations

import argparse
from pathlib import Path


def verify_bundle(bundle: Path) -> None:
    """Raise a descriptive error when required application files are absent."""
    if not bundle.exists():
        raise FileNotFoundError(f"Application bundle does not exist: {bundle}")
    files = [item for item in bundle.rglob("*") if item.is_file()]
    names = {item.name.lower() for item in files}
    if not ({"aurora", "aurora.exe"} & names):
        raise RuntimeError("Aurora executable is absent from the application bundle")
    if not ({"rigctld", "rigctld.exe"} & names):
        raise RuntimeError("Bundled Hamlib rigctld is absent from the application bundle")
    if "source.txt" not in names:
        raise RuntimeError("Bundled Hamlib provenance is absent from the application bundle")


def main() -> None:
    """Parse a bundle path and report successful verification."""
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    arguments = parser.parse_args()
    verify_bundle(arguments.bundle.resolve())
    print(f"Verified Aurora bundle: {arguments.bundle}")


if __name__ == "__main__":
    main()
