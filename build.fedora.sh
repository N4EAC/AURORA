#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_VENV="$PROJECT_ROOT/.venv-build-fedora"
VERSION="${AURORA_VERSION:-0.1.0}"

cd "$PROJECT_ROOT"
[[ "$(uname -s)" == "Linux" ]] || { echo "ERROR: Run this script on Fedora." >&2; exit 1; }
command -v rpmbuild >/dev/null || { echo "ERROR: rpm-build is required." >&2; exit 1; }
command -v "$PYTHON_BIN" >/dev/null || { echo "ERROR: Python 3 is required." >&2; exit 1; }

"$PYTHON_BIN" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
"$BUILD_VENV/bin/python" -m pip install -r requirements-build.txt
if [[ "${AURORA_SKIP_TESTS:-0}" != "1" ]]; then
    QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 \
        "$BUILD_VENV/bin/python" -m unittest discover -s tests -q
fi
"$BUILD_VENV/bin/python" tools/bootstrap_hamlib.py
"$BUILD_VENV/bin/python" packaging/stage_hamlib.py

rm -rf "$PROJECT_ROOT/build/pyinstaller-fedora" "$PROJECT_ROOT/dist/Aurora"
"$BUILD_VENV/bin/pyinstaller" --noconfirm --clean \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller-fedora" \
    "$PROJECT_ROOT/packaging/aurora.spec"
"$BUILD_VENV/bin/python" packaging/verify_bundle.py "$PROJECT_ROOT/dist/Aurora"

RPM_TOP="$PROJECT_ROOT/build/package-fedora"
SOURCE_DIR="$RPM_TOP/source/aurora-hf-modem-$VERSION"
rm -rf "$RPM_TOP"
mkdir -p "$RPM_TOP"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} "$SOURCE_DIR/app" "$PROJECT_ROOT/dist/installer"
cp -a "$PROJECT_ROOT/dist/Aurora/." "$SOURCE_DIR/app/"
cp packaging/linux/aurora.desktop "$SOURCE_DIR/"
cp Aurora_logo.png "$SOURCE_DIR/aurora.png"
tar -C "$RPM_TOP/source" -czf "$RPM_TOP/SOURCES/aurora-hf-modem-$VERSION.tar.gz" "aurora-hf-modem-$VERSION"
RPM_VERSION="${VERSION//-/.}"
RPM_ARCH="$(rpm --eval '%{_arch}')"
sed -e "s/@VERSION@/$VERSION/g" -e "s/@RPM_VERSION@/$RPM_VERSION/g" -e "s/@ARCH@/$RPM_ARCH/g" \
    packaging/linux/aurora-rpm.spec.in > "$RPM_TOP/SPECS/aurora-hf-modem.spec"
rpmbuild --define "_topdir $RPM_TOP" -bb "$RPM_TOP/SPECS/aurora-hf-modem.spec"
find "$RPM_TOP/RPMS" -name '*.rpm' -exec cp {} "$PROJECT_ROOT/dist/installer/" \;
PACKAGE="$(find "$PROJECT_ROOT/dist/installer" -maxdepth 1 -name "aurora-hf-modem-${RPM_VERSION}-1*.rpm" -print -quit)"
[[ -n "$PACKAGE" ]] || { echo "ERROR: rpmbuild did not produce an installer." >&2; exit 1; }
rpm -qpi "$PACKAGE" >/dev/null
echo "Installer complete: $PACKAGE"
