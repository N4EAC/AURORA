"""End-to-end tests for the Aurora DSP core."""

from dataclasses import replace
import unittest

from dsp import EncodedTransmission, FrameError, decode_transmission, encode_payload
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

    def test_interleaved_payload_round_trip(self) -> None:
        encoded = encode_payload(
            b"burst-resistant Aurora",
            flags=3,
            modulation="bpsk",
            interleaver_columns=16,
        )
        decoded = decode_transmission(encoded)
        self.assertEqual(decoded.payload, b"burst-resistant Aurora")
        self.assertEqual(decoded.flags, 3)
        self.assertEqual(encoded.interleaver_columns, 16)

    def test_interleaving_recovers_a_contiguous_symbol_burst(self) -> None:
        payload = b"burst"
        baseline = encode_payload(payload, modulation="bpsk")
        interleaved = encode_payload(
            payload, modulation="bpsk", interleaver_columns=16
        )

        def flip_burst(transmission: EncodedTransmission) -> EncodedTransmission:
            symbols = list(transmission.symbols)
            symbols[40:46] = [-symbol for symbol in symbols[40:46]]
            return replace(transmission, symbols=tuple(symbols))

        with self.assertRaises(FrameError):
            decode_transmission(flip_burst(baseline))
        self.assertEqual(
            decode_transmission(flip_burst(interleaved)).payload,
            payload,
        )


if __name__ == "__main__":
    unittest.main()
