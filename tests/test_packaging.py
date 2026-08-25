"""Tests for Aurora's cross-platform packaging helpers."""

from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

from tools import bootstrap_hamlib


VERIFY_PATH = Path(__file__).resolve().parent.parent / "packaging" / "verify_bundle.py"
VERIFY_SPEC = importlib.util.spec_from_file_location("aurora_verify_bundle", VERIFY_PATH)
assert VERIFY_SPEC is not None and VERIFY_SPEC.loader is not None
VERIFY_MODULE = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(VERIFY_MODULE)
verify_bundle = VERIFY_MODULE.verify_bundle


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
            verify_bundle(bundle)

    def test_bundle_rejects_missing_hamlib(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "Aurora.exe").touch()
            (bundle / "SOURCE.txt").touch()
            with self.assertRaisesRegex(RuntimeError, "rigctld"):
                verify_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
