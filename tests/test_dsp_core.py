"""End-to-end tests for the Aurora DSP core."""

import unittest

from dsp import decode_transmission, encode_payload
from dsp.core import bits_to_bytes, bytes_to_bits


class DspCoreTests(unittest.TestCase):
    def test_byte_bit_conversion(self) -> None:
        source = b"\x00\x5A\xFF"
        self.assertEqual(bits_to_bytes(bytes_to_bits(source)), source)

    def test_qpsk_payload_round_trip(self) -> None:
        encoded = encode_payload(b"Aurora on HF", flags=5)
        decoded = decode_transmission(encoded)
        self.assertEqual(decoded.payload, b"Aurora on HF")
        self.assertEqual(decoded.flags, 5)

    def test_bpsk_payload_round_trip(self) -> None:
        encoded = encode_payload(b"weak signal", modulation="bpsk")
        self.assertEqual(decode_transmission(encoded).payload, b"weak signal")


if __name__ == "__main__":
    unittest.main()
