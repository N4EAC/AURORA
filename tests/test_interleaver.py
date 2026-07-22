"""Tests for Aurora deterministic block interleaving."""

import unittest

from dsp.interleaver import block_deinterleave, block_interleave


class InterleaverTests(unittest.TestCase):
    def test_round_trip_supports_ragged_blocks(self) -> None:
        source = list(range(37))
        interleaved = block_interleave(source, columns=8)
        self.assertNotEqual(interleaved, source)
        self.assertEqual(block_deinterleave(interleaved, columns=8), source)

    def test_soft_values_preserve_exact_order_and_type(self) -> None:
        source = [0.25, -1.5, 3.0, -0.125, 8.75]
        restored = block_deinterleave(block_interleave(source, 3), 3)
        self.assertEqual(restored, source)

    def test_empty_sequence_is_supported(self) -> None:
        self.assertEqual(block_interleave([], 4), [])
        self.assertEqual(block_deinterleave([], 4), [])

    def test_invalid_column_count_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            block_interleave([1, 0], 0)


if __name__ == "__main__":
    unittest.main()
