"""Tests for Aurora CAT commands."""

import unittest
from unittest.mock import MagicMock, call

from radio.cat import CatController, CatProtocolError


class CatTests(unittest.TestCase):
    def test_frequency_and_mode_commands(self) -> None:
        transport = MagicMock()
        transport.query.side_effect = ["FA00014074000;", "MD2;"]
        cat = CatController(transport)

        cat.set_frequency(14_074_000)
        cat.set_mode("usb")
        self.assertEqual(cat.get_frequency(), 14_074_000)
        self.assertEqual(cat.get_mode(), "USB")
        self.assertEqual(
            transport.send.call_args_list,
            [call("FA00014074000;"), call("MD2;")],
        )

    def test_invalid_response_is_rejected(self) -> None:
        transport = MagicMock()
        transport.query.return_value = "BAD;"
        with self.assertRaises(CatProtocolError):
            CatController(transport).get_frequency()


if __name__ == "__main__":
    unittest.main()
