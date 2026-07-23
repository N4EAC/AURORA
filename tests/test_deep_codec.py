"""Tests for the research-only Aurora Deep payload codec."""

import unittest

from dsp.deep_codec import (
    K10_RATE_QUARTER_GENERATORS,
    DeepCodecConfig,
    combine_repeated_likelihoods,
    bounded_free_distance,
    decode_deep_likelihoods,
    encode_deep_payload,
    native_rate_quarter_decode_soft,
    native_rate_quarter_encode,
    polynomial_gcd,
)
from dsp.framing import FrameError


class DeepCodecTests(unittest.TestCase):
    def test_clean_twenty_byte_payload_round_trip(self) -> None:
        payload = b"Aurora Deep message!"
        for repetition in (1, 2):
            for columns in (16, 32):
                with self.subTest(repetition=repetition, columns=columns):
                    config = DeepCodecConfig(repetition, columns)
                    encoded = encode_deep_payload(payload, config)
                    likelihoods = [
                        12.0 if bit == 0 else -12.0 for bit in encoded.bits
                    ]
                    decoded = decode_deep_likelihoods(likelihoods, config)
                    self.assertEqual(decoded.payload, payload)

    def test_repetition_combining_increases_consistent_confidence(self) -> None:
        combined = combine_repeated_likelihoods(
            (0.5, 0.5, -0.25, -0.25),
            repetition=2,
        )
        self.assertEqual(combined, [1.0, -0.5])
        self.assertGreaterEqual(abs(combined[0]), 0.5)
        self.assertGreaterEqual(abs(combined[1]), 0.25)

    def test_interleaved_soft_values_preserve_decode_order(self) -> None:
        config = DeepCodecConfig(2, 32)
        encoded = encode_deep_payload(b"Aurora Deep message!", config)
        likelihoods = [20.0 if bit == 0 else -20.0 for bit in encoded.bits]
        self.assertEqual(
            decode_deep_likelihoods(likelihoods, config).payload,
            b"Aurora Deep message!",
        )

    def test_crc_rejects_corrupted_soft_payload(self) -> None:
        config = DeepCodecConfig(1, 16)
        encoded = encode_deep_payload(b"Aurora Deep message!", config)
        likelihoods = [-20.0 if bit == 0 else 20.0 for bit in encoded.bits]
        with self.assertRaises((FrameError, ValueError)):
            decode_deep_likelihoods(likelihoods, config)

    def test_nominal_code_rates_are_explicit(self) -> None:
        self.assertEqual(DeepCodecConfig(1, 16).nominal_code_rate, 0.5)
        self.assertEqual(DeepCodecConfig(2, 16).nominal_code_rate, 0.25)
        native = DeepCodecConfig(1, 16, "native_rate_quarter")
        self.assertEqual(native.nominal_code_rate, 0.25)

    def test_native_rate_quarter_payload_round_trip(self) -> None:
        config = DeepCodecConfig(1, 32, "native_rate_quarter")
        encoded = encode_deep_payload(b"Aurora Deep message!", config)
        likelihoods = [15.0 if bit == 0 else -15.0 for bit in encoded.bits]
        decoded = decode_deep_likelihoods(likelihoods, config)
        self.assertEqual(decoded.payload, b"Aurora Deep message!")

    def test_native_and_repeated_rate_quarter_have_equal_length(self) -> None:
        payload = b"Aurora Deep message!"
        repeated = encode_deep_payload(payload, DeepCodecConfig(2, 16))
        native = encode_deep_payload(
            payload,
            DeepCodecConfig(1, 16, "native_rate_quarter"),
        )
        self.assertEqual(len(native.bits), len(repeated.bits))

    def test_native_soft_decoder_recovers_flipped_observations(self) -> None:
        source = [0, 1, 1, 0, 1, 0] * 8
        encoded = native_rate_quarter_encode(source)
        likelihoods = [8.0 if bit == 0 else -8.0 for bit in encoded]
        for offset in range(0, len(likelihoods), 24):
            likelihoods[offset] *= -1.0
        self.assertEqual(native_rate_quarter_decode_soft(likelihoods), source)

    def test_native_decoder_rejects_incomplete_groups(self) -> None:
        with self.assertRaisesRegex(ValueError, "four-value"):
            native_rate_quarter_decode_soft([1.0, -1.0, 1.0])

    def test_k10_candidate_round_trip_and_generator_gcd(self) -> None:
        config = DeepCodecConfig(
            1,
            32,
            "native_rate_quarter",
            10,
            K10_RATE_QUARTER_GENERATORS,
        )
        encoded = encode_deep_payload(b"Aurora Deep message!", config)
        likelihoods = [20.0 if bit == 0 else -20.0 for bit in encoded.bits]
        self.assertEqual(
            decode_deep_likelihoods(likelihoods, config).payload,
            b"Aurora Deep message!",
        )
        self.assertEqual(len(encoded.bits), 996)
        self.assertEqual(polynomial_gcd(K10_RATE_QUARTER_GENERATORS), 1)
        self.assertGreaterEqual(
            bounded_free_distance(K10_RATE_QUARTER_GENERATORS, 10),
            20,
        )


if __name__ == "__main__":
    unittest.main()
