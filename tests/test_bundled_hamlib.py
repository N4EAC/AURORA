"""Tests for Aurora's private Hamlib service lifecycle."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from radio.bundled_hamlib import BundledHamlibConfig, BundledHamlibService
from radio.subprocess_support import hidden_process_kwargs
from tools.bootstrap_hamlib import platform_key, rigctld_path


class BundledHamlibTests(unittest.TestCase):
    def test_platform_runtime_path_is_inside_aurora(self) -> None:
        path = rigctld_path()
        self.assertIn("runtime/hamlib", path.as_posix())
        self.assertIn(platform_key(), path.as_posix())

    def test_config_requires_model_and_device(self) -> None:
        with self.assertRaisesRegex(ValueError, "model"):
            BundledHamlibConfig(0, "/dev/radio")
        with self.assertRaisesRegex(ValueError, "device"):
            BundledHamlibConfig(1, " ")

    def test_windows_background_process_has_no_console(self) -> None:
        options = hidden_process_kwargs("Windows")
        self.assertEqual(options["creationflags"], 0x08000000)
        self.assertEqual(hidden_process_kwargs("Linux"), {})

    def test_service_launches_localhost_only_and_stops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "rigctld"
            executable.touch()
            process = MagicMock()
            process.poll.return_value = None
            connection = MagicMock()
            with (
                patch("radio.bundled_hamlib.subprocess.Popen", return_value=process) as popen,
                patch("radio.bundled_hamlib.socket.create_connection", return_value=connection),
            ):
                service = BundledHamlibService(executable)
                service.start(BundledHamlibConfig(3073, "/dev/cu.radio", 19_200))
                self.assertTrue(service.running)
                service.stop()
            command = popen.call_args.args[0]
            self.assertEqual(command[1:3], ["-m", "3073"])
            self.assertIn("127.0.0.1", command)
            process.terminate.assert_called_once_with()

    def test_service_applies_windows_hidden_process_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "rigctld.exe"
            executable.touch()
            process = MagicMock()
            process.poll.return_value = None
            with (
                patch("radio.subprocess_support.platform.system", return_value="Windows"),
                patch("radio.bundled_hamlib.subprocess.Popen", return_value=process) as popen,
                patch("radio.bundled_hamlib.socket.create_connection"),
            ):
                service = BundledHamlibService(executable)
                service.start(BundledHamlibConfig(3073, "COM3"))
                service.stop()
            self.assertEqual(popen.call_args.kwargs["creationflags"], 0x08000000)


if __name__ == "__main__":
    unittest.main()
