"""Tests for Aurora's fixed-geometry AX.25 chat transport."""

import unittest

from dsp.core import decode_transmission
from modem.chat_transport import (
    CHAT_TEXT_BYTES,
    decode_chat_transport,
    encode_chat_transmission,
)


class ChatTransportTests(unittest.TestCase):
    def test_callsign_and_message_round_trip(self) -> None:
        first = encode_chat_transmission("N4EAC", "CQ from Aurora")
        second = encode_chat_transmission("W1AW", "short")
        decoded = decode_chat_transport(decode_transmission(first))
        self.assertEqual(decoded.callsign, "N4EAC")
        self.assertEqual(decoded.text, "CQ from Aurora")
        self.assertEqual(len(first.symbols), len(second.symbols))

    def test_message_limit_is_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, str(CHAT_TEXT_BYTES)):
            encode_chat_transmission("N4EAC", "x" * (CHAT_TEXT_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
