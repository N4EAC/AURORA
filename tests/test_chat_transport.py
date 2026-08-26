"""Tests for Aurora's variable-length native chat transport."""

import unittest
import struct

from dsp.core import decode_transmission
from modem.chat_transport import (
    CHAT_TEXT_BYTES,
    build_native_chat,
    decode_chat_transport,
    encode_chat_air_transmission,
    encode_chat_transmission,
)


class ChatTransportTests(unittest.TestCase):
    def test_callsign_and_message_round_trip(self) -> None:
        first = encode_chat_transmission("N4EAC", "CQ from Aurora")
        second = encode_chat_transmission("W1AW", "short")
        decoded = decode_chat_transport(decode_transmission(first))
        self.assertEqual(decoded.callsign, "N4EAC")
        self.assertEqual(decoded.text, "CQ from Aurora")
        self.assertLess(len(second.symbols), len(first.symbols))

    def test_native_chat_has_no_ax25_padding(self) -> None:
        short = build_native_chat("N4EAC", "x", frame_id=7)
        longer = build_native_chat("N4EAC", "a longer message", frame_id=7)
        self.assertEqual(len(longer) - len(short), len("a longer message") - 1)

    def test_air_transmission_has_protected_bootstrap(self) -> None:
        transmission = encode_chat_air_transmission(
            "N4EAC", "CQ", frame_id=0x12345678
        )
        self.assertGreater(transmission.bootstrap_symbol_count, 0)
        self.assertGreater(transmission.payload_symbol_count, 0)
        self.assertEqual(
            len(transmission.symbols),
            transmission.bootstrap_symbol_count + transmission.payload_symbol_count,
        )

    def test_message_limit_is_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, str(CHAT_TEXT_BYTES)):
            encode_chat_transmission("N4EAC", "x" * (CHAT_TEXT_BYTES + 1))

    def test_reply_channel_controls_round_trip(self) -> None:
        encoded = build_native_chat(
            "N4EAC",
            "Your turn",
            destination="W1AW",
            frame_id=9,
            sender_name="Eduardo",
            contact_id=77,
            reply_frequency_hz=7_107_000,
            reply_window_seconds=120,
            back_to_you=True,
        )
        from modem.chat_transport import parse_native_chat

        message = parse_native_chat(encoded)
        self.assertEqual(message.sender_name, "Eduardo")
        self.assertEqual(message.contact_id, 77)
        self.assertEqual(message.reply_frequency_hz, 7_107_000)
        self.assertTrue(message.back_to_you)
        self.assertFalse(message.end_of_call)

    def test_version_two_chat_remains_decodable(self) -> None:
        from modem.chat_transport import parse_native_chat

        source, target, text = b"N4EAC", b"AURORA", b"old recording"
        encoded = struct.pack(
            ">2sBIBBH", b"AC", 2, 4, len(source), len(target), len(text)
        ) + source + target + text
        message = parse_native_chat(encoded)
        self.assertEqual(message.text, "old recording")
        self.assertIsNone(message.reply_frequency_hz)


if __name__ == "__main__":
    unittest.main()
