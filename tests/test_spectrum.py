"""Tests for Aurora spectrum analysis."""

import unittest

import numpy as np

from dsp.spectrum import compute_spectrum


class SpectrumTests(unittest.TestCase):
    def test_real_tone_peak_has_expected_frequency(self) -> None:
        sample_rate = 12_000
        fft_size = 1_200
        indices = np.arange(fft_size)
        samples = np.sin(2.0 * np.pi * 1_000.0 * indices / sample_rate)
        frame = compute_spectrum(samples, sample_rate, fft_size=fft_size)
        peak_frequency = frame.frequencies_hz[np.argmax(frame.power_db)]
        self.assertAlmostEqual(float(peak_frequency), 1_000.0)

    def test_complex_negative_frequency_is_preserved(self) -> None:
        sample_rate = 8_000
        fft_size = 800
        indices = np.arange(fft_size)
        samples = np.exp(-2j * np.pi * 500.0 * indices / sample_rate)
        frame = compute_spectrum(samples, sample_rate, fft_size=fft_size)
        peak_frequency = frame.frequencies_hz[np.argmax(frame.power_db)]
        self.assertAlmostEqual(float(peak_frequency), -500.0)


if __name__ == "__main__":
    unittest.main()
