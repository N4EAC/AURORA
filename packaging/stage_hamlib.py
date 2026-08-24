"""Reduce a bootstrapped Hamlib prefix to Aurora's distributable runtime."""

from __future__ import annotations

from pathlib import Path
import platform
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from tools.bootstrap_hamlib import VERSION, platform_key, runtime_root


DOCUMENTS = ("COPYING", "COPYING.LIB", "LICENSE")


def stage_runtime() -> Path:
    """Validate Hamlib and add required licensing/provenance files."""
    root = runtime_root()
    suffix = ".exe" if platform.system() == "Windows" else ""
    executable = root / "bin" / f"rigctld{suffix}"
    if not executable.is_file():
        raise FileNotFoundError(f"Hamlib runtime is missing: {executable}")

    docs = root / "share" / "doc" / "hamlib"
    docs.mkdir(parents=True, exist_ok=True)
    existing_docs = [candidate for candidate in root.rglob("COPYING*")]
    existing_docs.extend(root.rglob("LICENSE"))
    for name in DOCUMENTS:
        target = docs / name
        if target.exists():
            continue
        source = next((item for item in existing_docs if item.name == name), None)
        if source is not None and source != target:
            shutil.copy2(source, target)
    (docs / "SOURCE.txt").write_text(
        f"Hamlib {VERSION} runtime bundled with Aurora\n"
        "Source: https://github.com/Hamlib/Hamlib/releases/tag/4.7.2\n"
        "Licenses: see COPYING, COPYING.LIB, and LICENSE when present.\n",
        encoding="utf-8",
    )
    return executable


if __name__ == "__main__":
    print(stage_runtime())
