"""Tests for Aurora serial radio transport."""

import unittest
from unittest.mock import MagicMock

from radio.transport import RadioConnectionError, SerialTransport


class RadioTransportTests(unittest.TestCase):
    def test_query_writes_ascii_and_reads_response(self) -> None:
        backend = MagicMock(is_open=True)
        backend.read_until.return_value = b"FA00014074000;"
        factory = MagicMock(return_value=backend)
        transport = SerialTransport("COM7", serial_factory=factory)

        self.assertEqual(transport.query("FA;"), "FA00014074000;")
        factory.assert_called_once_with(
            port="COM7", baudrate=9_600, timeout=0.5, write_timeout=0.5
        )
        backend.write.assert_called_once_with(b"FA;")
        backend.flush.assert_called_once_with()

    def test_incomplete_response_raises_timeout(self) -> None:
        backend = MagicMock(is_open=True)
        backend.read_until.return_value = b"FA"
        transport = SerialTransport(
            "COM7", serial_factory=MagicMock(return_value=backend)
        )
        with self.assertRaisesRegex(RadioConnectionError, "timed out"):
            transport.query("FA;")


if __name__ == "__main__":
    unittest.main()
