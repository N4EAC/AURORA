"""Build or unpack Aurora's private, checksum-verified Hamlib runtime."""

from __future__ import annotations

import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile


VERSION = "4.7.2"
SOURCE_URL = (
    "https://github.com/Hamlib/Hamlib/releases/download/4.7.2/"
    "hamlib-4.7.2.tar.gz"
)
SOURCE_SHA256 = "ae1fcf2dbc80ea0786ea8f047b09399c3f7737d1930442f61a031708ed33e88f"
WINDOWS_X64_URL = (
    "https://github.com/Hamlib/Hamlib/releases/download/4.7.2/"
    "hamlib-w64-4.7.2.zip"
)
WINDOWS_X64_SHA256 = "8553bc6c5c6032e8debf99c017e98f58fed7e07e7c25d04815dc3e8bbe3304c7"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def platform_key() -> str:
    """Return the normalized runtime directory key."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    aliases = {"amd64": "x86_64", "aarch64": "arm64"}
    return f"{system}-{aliases.get(machine, machine)}"


def runtime_root() -> Path:
    """Return the platform-specific private Hamlib prefix.

    Frozen applications read data from PyInstaller's private bundle directory;
    source checkouts retain the reproducible project-local runtime location.
    """
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root is not None:
        return Path(frozen_root) / "runtime" / "hamlib" / platform_key()
    return PROJECT_ROOT / "runtime" / "hamlib" / platform_key()


def rigctld_path() -> Path:
    """Return the expected bundled rigctld executable path."""
    suffix = ".exe" if platform.system() == "Windows" else ""
    return runtime_root() / "bin" / f"rigctld{suffix}"


def _download(url: str, expected_sha256: str, destination: Path) -> None:
    curl = shutil.which("curl")
    if curl is not None:
        subprocess.run(
            [curl, "-L", "--fail", "--output", str(destination), url],
            check=True,
        )
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)
    digest = hashlib.sha256(destination.read_bytes())
    if digest.hexdigest() != expected_sha256:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Hamlib download checksum verification failed")


def _build_source(archive: Path, prefix: Path, work: Path) -> None:
    with tarfile.open(archive, "r:gz") as source:
        source.extractall(work, filter="data")
    tree = work / f"hamlib-{VERSION}"
    subprocess.run(
        [
            str(tree / "configure"),
            f"--prefix={prefix}",
            "--disable-shared",
            "--enable-static",
            "--without-readline",
            "--without-libusb",
            "--without-xml-support",
        ],
        cwd=tree,
        check=True,
    )
    subprocess.run(["make", "-j2"], cwd=tree, check=True)
    subprocess.run(["make", "install"], cwd=tree, check=True)


def _unpack_windows(archive: Path, prefix: Path, work: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        source.extractall(work)
    executable = next(work.rglob("rigctld.exe"), None)
    if executable is None:
        raise RuntimeError("Official Hamlib archive does not contain rigctld.exe")
    source_root = executable.parent
    target = prefix / "bin"
    target.mkdir(parents=True, exist_ok=True)
    for item in source_root.iterdir():
        if item.is_file() and item.suffix.lower() in {".exe", ".dll"}:
            shutil.copy2(item, target / item.name)
    docs = prefix / "share" / "doc" / "hamlib"
    docs.mkdir(parents=True, exist_ok=True)
    for name in ("COPYING", "COPYING.LIB", "LICENSE"):
        source = next(work.rglob(name), None)
        if source is not None:
            shutil.copy2(source, docs / name)


def bootstrap(*, force: bool = False) -> Path:
    """Prepare and return Aurora's private rigctld executable."""
    executable = rigctld_path()
    if executable.exists() and not force:
        return executable
    prefix = runtime_root()
    if force and prefix.exists():
        shutil.rmtree(prefix)
    prefix.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aurora-hamlib-") as directory:
        work = Path(directory)
        if platform.system() == "Windows" and platform.machine().lower() in {
            "amd64",
            "x86_64",
        }:
            archive = work / "hamlib.zip"
            _download(WINDOWS_X64_URL, WINDOWS_X64_SHA256, archive)
            _unpack_windows(archive, prefix, work / "unpacked")
        else:
            archive = work / "hamlib.tar.gz"
            _download(SOURCE_URL, SOURCE_SHA256, archive)
            _build_source(archive, prefix, work / "source")
    if not executable.exists():
        raise RuntimeError("Bundled Hamlib build did not produce rigctld")
    return executable


if __name__ == "__main__":
    print(bootstrap())
