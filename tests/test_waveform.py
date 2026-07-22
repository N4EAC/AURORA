"""Tests for Aurora's experimental offline audio waveform."""

import unittest

import numpy as np

from dsp import decode_soft_symbols, encode_payload
from dsp.preamble import PREAMBLE_SYMBOL_COUNT
from dsp.waveform import (
    demodulate_audio,
    modulate_audio,
    occupied_bandwidth_hz,
    root_raised_cosine_taps,
    samples_per_symbol,
)
from modem import AURORA_ROBUST_MODE


class WaveformTests(unittest.TestCase):
    def test_mode_has_exact_audio_sampling_ratio(self) -> None:
        self.assertEqual(samples_per_symbol(), 384)

    def test_root_raised_cosine_is_symmetric_and_energy_normalized(self) -> None:
        taps = root_raised_cosine_taps(16, 0.35, 8)
        self.assertTrue(np.allclose(taps, taps[::-1]))
        self.assertAlmostEqual(float(np.sum(taps * taps)), 1.0)

    def test_modulation_is_deterministic_finite_and_does_not_clip(self) -> None:
        symbols = np.asarray([1.0, -1.0, 1.0, -1.0])
        first = modulate_audio(symbols)
        second = modulate_audio(symbols)
        self.assertTrue(np.array_equal(first.samples, second.samples))
        self.assertTrue(np.isfinite(first.samples).all())
        self.assertLessEqual(float(np.max(np.abs(first.samples))), 1.0)

        taps = root_raised_cosine_taps(
            samples_per_symbol(),
            AURORA_ROBUST_MODE.pulse_rolloff,
            AURORA_ROBUST_MODE.pulse_span_symbols,
        )
        expected = (
            (PREAMBLE_SYMBOL_COUNT + len(symbols)) * samples_per_symbol()
            + len(taps)
            - 1
        )
        self.assertEqual(first.frame_count, expected)

    def test_clean_symbols_round_trip_after_leading_silence(self) -> None:
        symbols = np.asarray([1.0, -1.0, -1.0, 1.0] * 6)
        audio = modulate_audio(symbols, leading_silence_samples=137)
        result = demodulate_audio(audio, len(symbols))
        decisions = np.where(result.symbols.real >= 0.0, 1.0, -1.0)
        self.assertTrue(np.array_equal(decisions, symbols))
        self.assertGreater(result.diagnostics.sync_metric, 0.9)
        self.assertTrue(result.diagnostics.synchronized)

    def test_frequency_offset_is_estimated_and_corrected(self) -> None:
        symbols = np.asarray([1.0, -1.0, 1.0, 1.0, -1.0] * 8)
        expected_offset = 0.08
        audio = modulate_audio(symbols, frequency_offset_hz=expected_offset)
        result = demodulate_audio(audio, len(symbols))
        decisions = np.where(result.symbols.real >= 0.0, 1.0, -1.0)
        self.assertTrue(np.array_equal(decisions, symbols))
        self.assertAlmostEqual(
            result.diagnostics.frequency_offset_hz,
            expected_offset,
            delta=0.01,
        )

    def test_codec_payload_round_trip_through_audio(self) -> None:
        mode = AURORA_ROBUST_MODE
        transmission = encode_payload(
            b"offline Aurora waveform",
            modulation=mode.modulation,
            interleaver_columns=mode.interleaver_columns,
        )
        audio = modulate_audio(transmission.symbols, mode)
        recovered = demodulate_audio(audio, len(transmission.symbols), mode)
        frame = decode_soft_symbols(
            tuple(recovered.symbols),
            mode.modulation,
            noise_variance=1e-4,
            interleaver_columns=mode.interleaver_columns,
        )
        self.assertEqual(frame.payload, b"offline Aurora waveform")

    def test_occupied_bandwidth_is_narrower_than_project_channel_limit(self) -> None:
        random = np.random.default_rng(2026)
        symbols = np.where(random.integers(0, 2, 512) == 0, 1.0, -1.0)
        bandwidth = occupied_bandwidth_hz(modulate_audio(symbols))
        self.assertGreater(bandwidth, AURORA_ROBUST_MODE.symbol_rate)
        self.assertLess(bandwidth, 100.0)


if __name__ == "__main__":
    unittest.main()
