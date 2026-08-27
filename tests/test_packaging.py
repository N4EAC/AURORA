"""Tests for Aurora's cross-platform packaging helpers."""

from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

import aurora
from tools import bootstrap_hamlib


VERIFY_PATH = Path(__file__).resolve().parent.parent / "packaging" / "verify_bundle.py"
SPEC_PATH = Path(__file__).resolve().parent.parent / "packaging" / "aurora.spec"
OPERATOR_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "packaging"
    / "validate_operator_configuration.py"
)
BUILD_PREFLIGHT_PATH = (
    Path(__file__).resolve().parent.parent / "packaging" / "build_preflight.py"
)
VERIFY_SPEC = importlib.util.spec_from_file_location("aurora_verify_bundle", VERIFY_PATH)
assert VERIFY_SPEC is not None and VERIFY_SPEC.loader is not None
VERIFY_MODULE = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(VERIFY_MODULE)
verify_bundle = VERIFY_MODULE.verify_bundle

OPERATOR_CONFIG_SPEC = importlib.util.spec_from_file_location(
    "aurora_operator_build_config", OPERATOR_CONFIG_PATH
)
assert OPERATOR_CONFIG_SPEC is not None and OPERATOR_CONFIG_SPEC.loader is not None
OPERATOR_CONFIG_MODULE = importlib.util.module_from_spec(OPERATOR_CONFIG_SPEC)
OPERATOR_CONFIG_SPEC.loader.exec_module(OPERATOR_CONFIG_MODULE)

BUILD_PREFLIGHT_SPEC = importlib.util.spec_from_file_location(
    "aurora_build_preflight", BUILD_PREFLIGHT_PATH
)
assert BUILD_PREFLIGHT_SPEC is not None and BUILD_PREFLIGHT_SPEC.loader is not None
BUILD_PREFLIGHT_MODULE = importlib.util.module_from_spec(BUILD_PREFLIGHT_SPEC)
BUILD_PREFLIGHT_SPEC.loader.exec_module(BUILD_PREFLIGHT_MODULE)


class PackagingTests(unittest.TestCase):
    """Verify frozen-runtime discovery and bundle validation."""

    def test_runtime_root_uses_pyinstaller_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(bootstrap_hamlib.sys, "_MEIPASS", directory, create=True):
                expected = Path(directory) / "runtime" / "hamlib"
                self.assertEqual(bootstrap_hamlib.runtime_root().parent, expected)

    def test_bundle_requires_application_hamlib_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "Aurora").touch()
            (bundle / "rigctld").touch()
            (bundle / "SOURCE.txt").touch()
            (bundle / "aurora-icon.png").touch()
            verify_bundle(bundle)

    def test_bundle_rejects_missing_hamlib(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "Aurora.exe").touch()
            (bundle / "SOURCE.txt").touch()
            with self.assertRaisesRegex(RuntimeError, "rigctld"):
                verify_bundle(bundle)

    def test_frozen_application_rejects_source_only_tk_ui(self) -> None:
        with patch.object(aurora.sys, "frozen", True, create=True):
            with self.assertRaisesRegex(RuntimeError, "Qt UI only"):
                aurora.select_ui_runner(["--tk"])

    def test_spec_includes_qt_entry_and_excludes_tk(self) -> None:
        specification = SPEC_PATH.read_text(encoding="utf-8")
        self.assertIn('"gui.qt_application"', specification)
        self.assertIn('"modem.contact_session"', specification)
        self.assertIn('"radio.split_control"', specification)
        self.assertIn('"tkinter"', specification)
        self.assertIn('"_tkinter"', specification)

    def test_operator_tuning_configuration_is_release_compatible(self) -> None:
        OPERATOR_CONFIG_MODULE.validate()
        project_root = Path(__file__).resolve().parent.parent
        for script in (
            "build.macos.sh",
            "build.ubuntu.sh",
            "build.fedora.sh",
            "build.exe.bat",
        ):
            self.assertIn(
                "validate_operator_configuration.py",
                (project_root / script).read_text(encoding="utf-8"),
            )

    def test_every_native_builder_runs_preflight_and_creates_output_root(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        for script in (
            "build.macos.sh",
            "build.ubuntu.sh",
            "build.fedora.sh",
            "build.exe.bat",
        ):
            contents = (project_root / script).read_text(encoding="utf-8")
            preflight_path = (
                "packaging\\build_preflight.py"
                if script.endswith(".bat")
                else "packaging/build_preflight.py"
            )
            self.assertIn(preflight_path, contents)
            self.assertIn("dist", contents)
            self.assertIn("installer", contents)

    def test_build_preflight_rejects_invalid_version(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "semantic"):
            BUILD_PREFLIGHT_MODULE.validate("macOS", "version-one")


if __name__ == "__main__":
    unittest.main()
