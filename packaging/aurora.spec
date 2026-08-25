"""PyInstaller definition shared by Aurora's native build scripts."""

from pathlib import Path
import platform

from PyInstaller.building.build_main import Analysis
from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.osx import BUNDLE


PROJECT_ROOT = Path(SPECPATH).parent
MACHINE_ALIASES = {"amd64": "x86_64", "aarch64": "arm64"}
machine = platform.machine().lower()
PLATFORM_KEY = (
    f"{platform.system().lower()}-{MACHINE_ALIASES.get(machine, machine)}"
)
HAMLIB_ROOT = PROJECT_ROOT / "runtime" / "hamlib" / PLATFORM_KEY
RIGCTLD = HAMLIB_ROOT / "bin" / (
    "rigctld.exe" if platform.system() == "Windows" else "rigctld"
)
HAMLIB_DOCS = HAMLIB_ROOT / "share" / "doc" / "hamlib"

if not RIGCTLD.is_file():
    raise SystemExit(f"Bundled Hamlib executable is missing: {RIGCTLD}")

VERSION_FILE = PROJECT_ROOT / "build" / "generated" / "aurora-version.txt"
if not VERSION_FILE.is_file():
    raise SystemExit(
        "Build metadata is missing; run packaging/prepare_build.py first"
    )

datas = [
    (str(PROJECT_ROOT / "Aurora_logo.png"), "."),
    (str(VERSION_FILE), "."),
]
binaries = [(str(RIGCTLD), f"runtime/hamlib/{PLATFORM_KEY}/bin")]
if platform.system() == "Windows":
    binaries.extend(
        (str(library), f"runtime/hamlib/{PLATFORM_KEY}/bin")
        for library in sorted((HAMLIB_ROOT / "bin").glob("*.dll"))
    )
for name in ("COPYING", "COPYING.LIB", "LICENSE", "SOURCE.txt"):
    source = HAMLIB_DOCS / name
    if source.is_file():
        datas.append((str(source), f"runtime/hamlib/{PLATFORM_KEY}/share/doc/hamlib"))

analysis = Analysis(
    [str(PROJECT_ROOT / "aurora.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["serial.tools.list_ports", "sounddevice"],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Aurora",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="Aurora",
)

if platform.system() == "Darwin":
    application = BUNDLE(
        collection,
        name="Aurora.app",
        bundle_identifier="org.n4eac.aurora",
        info_plist={
            "CFBundleDisplayName": "Aurora",
            "CFBundleName": "Aurora",
            "NSHighResolutionCapable": True,
        },
    )
