"""Tests for Aurora frequency-offset processing."""

import math
import unittest

import numpy as np

from dsp.frequency_offset import correct_frequency_offset, estimate_frequency_offset
from dsp.preamble import acquisition_preamble


class FrequencyOffsetTests(unittest.TestCase):
    def test_positive_offset_is_estimated_and_corrected(self) -> None:
        sample_rate = 12_000.0
        expected_offset = 23.5
        reference = acquisition_preamble(4)
        indices = np.arange(len(reference))
        received = reference * np.exp(
            2j * math.pi * expected_offset * indices / sample_rate
        )
        estimated = estimate_frequency_offset(received, reference, sample_rate)
        corrected = correct_frequency_offset(received, estimated, sample_rate)
        self.assertAlmostEqual(estimated, expected_offset, places=6)
        np.testing.assert_allclose(corrected, reference, atol=1e-10)

    def test_negative_offset_is_estimated(self) -> None:
        sample_rate = 12_000.0
        expected_offset = -31.25
        reference = acquisition_preamble(2)
        indices = np.arange(len(reference))
        received = reference * np.exp(
            2j * math.pi * expected_offset * indices / sample_rate
        )
        estimated = estimate_frequency_offset(received, reference, sample_rate)
        self.assertAlmostEqual(estimated, expected_offset, places=6)


if __name__ == "__main__":
    unittest.main()
