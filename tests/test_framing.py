"""Tests for Aurora binary framing."""

import unittest

from dsp.framing import FrameError, build_frame, parse_frame


class FramingTests(unittest.TestCase):
    def test_frame_round_trip(self) -> None:
        decoded = parse_frame(build_frame(b"CQ CQ", flags=3))
        self.assertEqual(decoded.payload, b"CQ CQ")
        self.assertEqual(decoded.flags, 3)
        self.assertEqual(decoded.version, 1)

    def test_crc_detects_corruption(self) -> None:
        encoded = bytearray(build_frame(b"payload"))
        encoded[-3] ^= 0x01
        with self.assertRaisesRegex(FrameError, "CRC"):
            parse_frame(encoded)

    def test_length_validation(self) -> None:
        with self.assertRaisesRegex(FrameError, "length"):
            parse_frame(build_frame(b"payload")[:-1])


if __name__ == "__main__":
    unittest.main()
