"""Tests for Aurora bit scrambling."""

import unittest

from dsp.scrambler import scramble_bits


class ScramblerTests(unittest.TestCase):
    def test_scrambling_is_reversible(self) -> None:
        source = [0, 1, 1, 0, 1, 0, 0, 1] * 8
        self.assertEqual(scramble_bits(scramble_bits(source)), source)

    def test_invalid_seed_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "seed"):
            scramble_bits([0, 1], seed=0)


if __name__ == "__main__":
    unittest.main()
