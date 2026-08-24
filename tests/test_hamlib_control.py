"""Tests for Aurora's Hamlib rigctld client without radio hardware."""

import io
import unittest
from unittest.mock import MagicMock

from radio.hamlib_control import HamlibController, HamlibError


class HamlibControlTests(unittest.TestCase):
    class FakeStream:
        def __init__(self, responses: bytes) -> None:
            self.responses = io.BytesIO(responses)
            self.commands = io.BytesIO()

        def write(self, data: bytes) -> int:
            return self.commands.write(data)

        def readline(self) -> bytes:
            return self.responses.readline()

        def close(self) -> None:
            pass

    def controller(self, responses: bytes):
        stream = self.FakeStream(responses)
        connection = MagicMock()
        connection.makefile.return_value = stream
        factory = MagicMock(return_value=connection)
        return HamlibController(connection_factory=factory), stream, factory

    def test_frequency_mode_and_ptt_queries(self) -> None:
        controller, stream, factory = self.controller(b"14074000\nUSB-D\n2800\n0\n")
        self.assertEqual(controller.get_frequency(), 14_074_000)
        self.assertEqual(controller.get_mode(), ("USB-D", 2_800))
        self.assertFalse(controller.get_ptt())
        factory.assert_called_once_with(("127.0.0.1", 4_532), timeout=1.0)
        self.assertEqual(stream.commands.getvalue(), b"f\nm\nt\n")

    def test_setters_require_success_response(self) -> None:
        controller, _, _ = self.controller(b"RPRT 0\nRPRT 0\nRPRT 0\n")
        controller.set_frequency(14_074_000)
        controller.set_mode("USB-D", 2_800)
        controller.set_ptt(False)

    def test_hamlib_error_is_reported(self) -> None:
        controller, _, _ = self.controller(b"RPRT -1\n")
        with self.assertRaises(HamlibError):
            controller.set_frequency(14_074_000)


if __name__ == "__main__":
    unittest.main()
