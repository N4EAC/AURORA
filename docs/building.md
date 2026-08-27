# Building Aurora installers

Aurora's release builds are self-contained desktop applications. Each build
includes Python, Qt, Aurora's dependencies, and the private Hamlib `rigctld`
runtime. End users do not need Python, Hamlib, or Inno Setup.
Native packages contain the supported Qt interface and intentionally exclude
the source-only Tk compatibility interface. Linux builds therefore do not
require the separately packaged `python3-tk` module.

Build on the target operating system. PyInstaller output is platform-specific;
cross-compiling these installers is not supported.

## Common controls

- `AURORA_VERSION` selects the semantic package version and defaults to `0.1.0`.
- `PYTHON_BIN` selects the build-machine Python interpreter.
- `AURORA_SKIP_TESTS=1` skips the pre-build test suite for diagnostic rebuilds.

Release builds should not skip tests. Generated output is written beneath
`dist/`; temporary output and isolated build environments are ignored by Git.
Every builder creates `dist/installer` before dependency installation begins,
so the output root is present even if a later stage fails. Failures identify
the active stage (preflight, dependencies, tests, Hamlib, PyInstaller, or native
installer) instead of reporting only a generic build failure.
The selected version is embedded in the application, About dialog, session
log, native package metadata, and installer filename. Invalid semantic versions
stop the build before packaging.
PyInstaller caches are isolated beneath `build/` so packaging does not depend
on or modify a user-level PyInstaller cache.
Every platform script also validates the operator tuning contract before
packaging: Hamlib controls RF frequency, Aurora's modem center is fixed at
1,500 Hz, and the receive scan covers the 100–3,000 Hz audio passband.

## macOS

Requirements are Python 3, Xcode command-line tools, and standard build tools.
The Hamlib bootstrap builds its pinned, checksum-verified source release.

```zsh
./build.macos.sh
```

The script creates `dist/Aurora.app`, applies an ad-hoc signature by default,
and creates `dist/installer/Aurora-<version>-macos-<architecture>.dmg`. Set
`AURORA_CODESIGN_IDENTITY` to a Developer ID identity for signed releases.
Notarization is intentionally a separate release credential step.

## Ubuntu

Install the build-machine prerequisites:

```bash
sudo apt install build-essential python3 python3-venv dpkg-dev
./build.ubuntu.sh
```

The result is `dist/installer/aurora-hf-modem_<version>_<architecture>.deb`.
It installs the application beneath `/opt/aurora` and adds the `aurora`
launcher and desktop entry.

## Fedora

Install the build-machine prerequisites:

```bash
sudo dnf install gcc gcc-c++ make python3 rpm-build
./build.fedora.sh
```

The resulting RPM is written beneath `dist/installer/`. It contains the same
self-contained application layout as the Ubuntu package.

## Windows

Install Python 3 and Inno Setup 6 on the build machine, then run:

```bat
build.exe.bat
```

The script creates `dist\Aurora\Aurora.exe` and then compiles
`dist\installer\Aurora-<version>-windows-x86_64-setup.exe` using
`packaging\windows\Aurora.iss`. If Inno Setup is installed in a custom
location, set `ISCC_EXE` to the full path of `ISCC.exe` before building.
The script uses absolute PyInstaller output paths and verifies both the EXE and
the expected installer before reporting success.

The Windows installer is per-user and therefore does not require administrator
rights. It provides Start menu and optional desktop shortcuts.

## Validation boundaries

Each script runs the complete unit test suite and validates that the generated
application contains both the Aurora executable and private Hamlib service.
The macOS build can only validate macOS output; Ubuntu, Fedora, and Windows
installers must be built and exercised on their respective systems.
