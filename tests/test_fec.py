"""Tests for Aurora forward error correction."""

import unittest

from dsp.fec import convolutional_encode, viterbi_decode


class FecTests(unittest.TestCase):
    def test_fec_round_trip(self) -> None:
        source = [1, 0, 1, 1, 0, 0, 1, 0] * 4
        self.assertEqual(viterbi_decode(convolutional_encode(source)), source)

    def test_single_encoded_bit_error_is_corrected(self) -> None:
        source = [1, 1, 0, 1, 0, 1, 1, 0] * 6
        encoded = convolutional_encode(source)
        encoded[len(encoded) // 2] ^= 1
        self.assertEqual(viterbi_decode(encoded), source)

    def test_incomplete_pair_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "pairs"):
            viterbi_decode([0, 1, 0])


if __name__ == "__main__":
    unittest.main()
