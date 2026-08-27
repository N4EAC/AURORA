#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_VENV="$PROJECT_ROOT/.venv-build-ubuntu"
VERSION="${AURORA_VERSION:-0.1.0}"
export PYINSTALLER_CONFIG_DIR="$PROJECT_ROOT/build/pyinstaller-config-ubuntu"
BUILD_STAGE="startup"
trap 'status=$?; echo "ERROR: Aurora Ubuntu build failed during $BUILD_STAGE (exit $status)." >&2' ERR

cd "$PROJECT_ROOT"
mkdir -p "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist/installer"
[[ "$(uname -s)" == "Linux" ]] || { echo "ERROR: Run this script on Ubuntu." >&2; exit 1; }
command -v dpkg-deb >/dev/null || { echo "ERROR: dpkg-deb is required." >&2; exit 1; }
command -v "$PYTHON_BIN" >/dev/null || { echo "ERROR: Python 3 is required." >&2; exit 1; }

BUILD_STAGE="build preflight"
"$PYTHON_BIN" packaging/build_preflight.py Ubuntu "$VERSION"
BUILD_STAGE="virtual environment creation"
"$PYTHON_BIN" -m venv "$BUILD_VENV"
BUILD_STAGE="Python build dependencies"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
"$BUILD_VENV/bin/python" -m pip install -r requirements-build.txt
if [[ "${AURORA_SKIP_TESTS:-0}" != "1" ]]; then
    BUILD_STAGE="test suite"
    QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 \
        "$BUILD_VENV/bin/python" -m unittest discover -s tests -q
fi
BUILD_STAGE="build metadata and bundled Hamlib"
"$BUILD_VENV/bin/python" packaging/prepare_build.py "$VERSION"
"$BUILD_VENV/bin/python" packaging/validate_operator_configuration.py
"$BUILD_VENV/bin/python" tools/bootstrap_hamlib.py
"$BUILD_VENV/bin/python" packaging/stage_hamlib.py

BUILD_STAGE="PyInstaller application"
rm -rf "$PROJECT_ROOT/build/pyinstaller-ubuntu" "$PROJECT_ROOT/dist/Aurora"
"$BUILD_VENV/bin/python" -m PyInstaller --noconfirm --clean \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller-ubuntu" \
    "$PROJECT_ROOT/packaging/aurora.spec"
[[ -x "$PROJECT_ROOT/dist/Aurora/Aurora" ]] || {
    echo "ERROR: PyInstaller did not create dist/Aurora/Aurora." >&2
    exit 1
}
"$BUILD_VENV/bin/python" packaging/verify_bundle.py "$PROJECT_ROOT/dist/Aurora"

BUILD_STAGE="DEB installer"
ARCH="$(dpkg --print-architecture)"
STAGE="$PROJECT_ROOT/build/package-ubuntu"
PACKAGE="$PROJECT_ROOT/dist/installer/aurora-hf-modem_${VERSION}_${ARCH}.deb"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/opt/aurora" "$STAGE/usr/bin" \
    "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/256x256/apps" \
    "$PROJECT_ROOT/dist/installer"
cp -a "$PROJECT_ROOT/dist/Aurora/." "$STAGE/opt/aurora/"
ln -s ../../opt/aurora/Aurora "$STAGE/usr/bin/aurora"
sed -e "s/@VERSION@/$VERSION/g" -e "s/@ARCH@/$ARCH/g" \
    packaging/linux/debian-control.in > "$STAGE/DEBIAN/control"
install -m 0644 packaging/linux/aurora.desktop "$STAGE/usr/share/applications/aurora.desktop"
install -m 0644 assets/aurora-icon.png "$STAGE/usr/share/icons/hicolor/256x256/apps/aurora.png"
dpkg-deb --build --root-owner-group "$STAGE" "$PACKAGE"
dpkg-deb --info "$PACKAGE" >/dev/null
BUILD_STAGE="complete"
echo "Installer complete: $PACKAGE"
