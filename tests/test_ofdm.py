"""Tests for Aurora's primary OFDM physical waveform."""

import unittest

import numpy as np

from dsp.core import decode_soft_symbols, encode_payload
from dsp.ofdm import DEFAULT_OFDM_CONFIG, frame_sample_count
from dsp.waveform import demodulate_audio, modulate_audio, occupied_bandwidth_hz
from modem import AURORA_ROBUST_MODE


class OfdmWaveformTests(unittest.TestCase):
    """Verify clean acquisition and the project's channel-width constraint."""

    def test_mode_selects_ofdm(self) -> None:
        self.assertEqual(AURORA_ROBUST_MODE.waveform, "ofdm")
        self.assertEqual(AURORA_ROBUST_MODE.pulse_shape, "ofdm")
        self.assertEqual(DEFAULT_OFDM_CONFIG.fft_size, 256)
        self.assertEqual(DEFAULT_OFDM_CONFIG.cyclic_prefix_samples, 64)
        self.assertLess(DEFAULT_OFDM_CONFIG.occupied_span_hz, 1_000.0)

    def test_known_symbols_round_trip_with_frequency_offset(self) -> None:
        symbols = np.where(np.arange(73) % 3, 1.0, -1.0)
        audio = modulate_audio(
            symbols,
            leading_silence_samples=211,
            frequency_offset_hz=2.0,
        )
        result = demodulate_audio(audio, len(symbols))
        decisions = np.where(result.symbols.real >= 0.0, 1.0, -1.0)
        self.assertTrue(np.array_equal(decisions, symbols))
        self.assertAlmostEqual(result.diagnostics.frequency_offset_hz, 2.0, delta=0.1)

    def test_codec_round_trip_through_ofdm_audio(self) -> None:
        transmission = encode_payload(
            b"Aurora OFDM",
            modulation=AURORA_ROBUST_MODE.modulation,
            interleaver_columns=AURORA_ROBUST_MODE.interleaver_columns,
        )
        audio = modulate_audio(transmission.symbols)
        recovered = demodulate_audio(audio, len(transmission.symbols))
        frame = decode_soft_symbols(
            tuple(recovered.symbols),
            AURORA_ROBUST_MODE.modulation,
            noise_variance=1e-4,
            interleaver_columns=AURORA_ROBUST_MODE.interleaver_columns,
        )
        self.assertEqual(frame.payload, b"Aurora OFDM")
        self.assertEqual(
            audio.frame_count,
            frame_sample_count(len(transmission.symbols)),
        )

    def test_occupied_bandwidth_stays_below_one_kilohertz(self) -> None:
        random = np.random.default_rng(2026)
        symbols = np.where(random.integers(0, 2, 1_024) == 0, 1.0, -1.0)
        bandwidth = occupied_bandwidth_hz(modulate_audio(symbols))
        self.assertGreater(bandwidth, 700.0)
        self.assertLess(bandwidth, 1_000.0)


if __name__ == "__main__":
    unittest.main()
