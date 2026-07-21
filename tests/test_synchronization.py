"""Tests for Aurora preamble synchronization."""

import unittest

import numpy as np

from dsp.preamble import acquisition_preamble
from dsp.synchronization import find_preamble


class SynchronizationTests(unittest.TestCase):
    def test_preamble_is_located_in_noise(self) -> None:
        random = np.random.default_rng(1200)
        preamble = acquisition_preamble(2)
        prefix = 0.05 * (
            random.normal(size=37) + 1j * random.normal(size=37)
        )
        received = np.concatenate((prefix, preamble, np.zeros(12)))
        result = find_preamble(received, preamble, threshold=0.8)
        self.assertTrue(result.locked)
        self.assertEqual(result.sample_index, 37)
        self.assertGreater(result.metric, 0.99)

    def test_silence_does_not_lock(self) -> None:
        preamble = acquisition_preamble()
        result = find_preamble(np.zeros(100), preamble)
        self.assertFalse(result.locked)
        self.assertEqual(result.metric, 0.0)


if __name__ == "__main__":
    unittest.main()
