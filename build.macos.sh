#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="${0:A:h}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_VENV="$PROJECT_ROOT/.venv-build-macos"
VERSION="${AURORA_VERSION:-0.1.0}"
ARCH="$(uname -m)"
export PYINSTALLER_CONFIG_DIR="$PROJECT_ROOT/build/pyinstaller-config-macos"
BUILD_STAGE="startup"
trap 'exit_code=$?; print -u2 "ERROR: Aurora macOS build failed during $BUILD_STAGE (exit $exit_code)."' ZERR

cd "$PROJECT_ROOT"
mkdir -p "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist/installer"
[[ "$(uname -s)" == "Darwin" ]] || { print -u2 "ERROR: Run this script on macOS."; exit 1; }
command -v "$PYTHON_BIN" >/dev/null || { print -u2 "ERROR: Python 3 is required."; exit 1; }
command -v codesign >/dev/null || { print -u2 "ERROR: Xcode command-line tools are required."; exit 1; }
command -v hdiutil >/dev/null || { print -u2 "ERROR: hdiutil is required."; exit 1; }

BUILD_STAGE="build preflight"
"$PYTHON_BIN" packaging/build_preflight.py macOS "$VERSION"
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
BUILD_STAGE="build metadata"
"$BUILD_VENV/bin/python" packaging/prepare_build.py "$VERSION"
"$BUILD_VENV/bin/python" packaging/validate_operator_configuration.py
"$BUILD_VENV/bin/python" tools/bootstrap_hamlib.py
"$BUILD_VENV/bin/python" packaging/stage_hamlib.py

BUILD_STAGE="PyInstaller application"
rm -rf "$PROJECT_ROOT/build/pyinstaller-macos" "$PROJECT_ROOT/dist/Aurora" "$PROJECT_ROOT/dist/Aurora.app"
"$BUILD_VENV/bin/python" -m PyInstaller --noconfirm --clean \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller-macos" \
    "$PROJECT_ROOT/packaging/aurora.spec"

APP="$PROJECT_ROOT/dist/Aurora.app"
[[ -d "$APP" ]] || { print -u2 "ERROR: PyInstaller did not create $APP"; exit 1; }
BUILD_STAGE="application signing and verification"
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Delete :CFBundleVersion" "$PLIST" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$PLIST"
codesign --force --deep --sign "${AURORA_CODESIGN_IDENTITY:--}" "$APP"
"$BUILD_VENV/bin/python" packaging/verify_bundle.py "$APP"

DMG_STAGE="$PROJECT_ROOT/build/dmg-macos"
DMG="$PROJECT_ROOT/dist/installer/Aurora-$VERSION-macos-$ARCH.dmg"
BUILD_STAGE="DMG installer"
rm -rf "$DMG_STAGE"
mkdir -p "$DMG_STAGE" "$PROJECT_ROOT/dist/installer"
cp -R "$APP" "$DMG_STAGE/Aurora.app"
ln -s /Applications "$DMG_STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "Aurora $VERSION" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG"
print "Build complete: $APP"
print "Installer complete: $DMG"
