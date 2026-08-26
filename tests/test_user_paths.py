"""Tests for writable source and frozen Aurora runtime paths."""

from pathlib import Path
import unittest

from util.user_paths import (
    PROJECT_ROOT,
    application_data_directory,
    application_log_directory,
)


class UserPathTests(unittest.TestCase):
    """Verify that installed applications never write inside their bundle."""

    def test_source_checkout_uses_project_directories(self) -> None:
        self.assertEqual(application_log_directory(frozen=False), PROJECT_ROOT / "logs")
        self.assertEqual(application_data_directory(frozen=False), PROJECT_ROOT / "data")

    def test_frozen_linux_uses_xdg_defaults(self) -> None:
        home = Path("/home/operator")
        self.assertEqual(
            application_log_directory(
                frozen=True, system="Linux", environment={}, home=home
            ),
            home / ".local/state/Aurora/logs",
        )
        self.assertEqual(
            application_data_directory(
                frozen=True, system="Linux", environment={}, home=home
            ),
            home / ".local/share/Aurora",
        )

    def test_frozen_linux_honors_xdg_overrides(self) -> None:
        environment = {
            "XDG_STATE_HOME": "/tmp/operator-state",
            "XDG_DATA_HOME": "/tmp/operator-data",
        }
        self.assertEqual(
            application_log_directory(
                frozen=True, system="Linux", environment=environment
            ),
            Path("/tmp/operator-state/Aurora/logs"),
        )
        self.assertEqual(
            application_data_directory(
                frozen=True, system="Linux", environment=environment
            ),
            Path("/tmp/operator-data/Aurora"),
        )

    def test_frozen_macos_and_windows_use_user_locations(self) -> None:
        home = Path("/Users/operator")
        self.assertEqual(
            application_log_directory(frozen=True, system="Darwin", home=home),
            home / "Library/Logs/Aurora",
        )
        self.assertEqual(
            application_data_directory(frozen=True, system="Darwin", home=home),
            home / "Library/Application Support/Aurora",
        )
        environment = {"LOCALAPPDATA": r"C:\Users\operator\AppData\Local"}
        self.assertEqual(
            application_log_directory(
                frozen=True, system="Windows", environment=environment
            ),
            Path(environment["LOCALAPPDATA"]) / "Aurora/logs",
        )


if __name__ == "__main__":
    unittest.main()
