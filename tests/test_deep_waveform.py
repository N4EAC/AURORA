"""Tests for the offline Aurora Deep research waveform."""

import unittest

import numpy as np

from audio.buffer import AudioBuffer
from dsp.audio_channel import AudioChannelConfig, apply_audio_channel
from dsp.deep_codec import decode_deep_likelihoods, encode_deep_payload
from dsp.deep_waveform import (
    DEEP_SYMBOL_RATE,
    bits_to_bpsk,
    deep_pilot_overhead,
    deep_pilot_symbols,
    modulate_deep_audio,
    multiplex_deep_pilots,
    recover_deep_likelihoods,
    recover_deep_candidate_likelihoods,
)
from dsp.waveform import occupied_bandwidth_hz


class DeepWaveformTests(unittest.TestCase):
    def test_bpsk_mapping_is_normalized_and_read_only(self) -> None:
        symbols = bits_to_bpsk([0, 1, 1, 0])
        self.assertTrue(np.array_equal(symbols.real, [1.0, -1.0, -1.0, 1.0]))
        self.assertFalse(symbols.flags.writeable)

    def test_clean_audio_recovers_payload_and_reports_duration(self) -> None:
        payload = b"Aurora Deep message!"
        encoded = encode_deep_payload(payload)
        audio = modulate_deep_audio(encoded.bits, leading_silence_samples=731)
        recovered = recover_deep_likelihoods(audio, len(encoded.bits))
        decoded = decode_deep_likelihoods(recovered.likelihoods, encoded.config)
        self.assertEqual(decoded.payload, payload)
        self.assertGreater(audio.duration_seconds, 30.0)
        self.assertLess(audio.duration_seconds, 40.0)
        self.assertEqual(DEEP_SYMBOL_RATE, 31.25)

    def test_frequency_and_clock_hypotheses_recover_payload(self) -> None:
        payload = b"Aurora Deep message!"
        encoded = encode_deep_payload(payload)
        audio = modulate_deep_audio(encoded.bits, frequency_offset_hz=2.0)
        impaired = apply_audio_channel(
            audio,
            AudioChannelConfig(clock_error_ppm=75.0),
            np.random.default_rng(7),
        )
        recovered = recover_deep_likelihoods(
            impaired,
            len(encoded.bits),
            clock_search_ppm=(0.0, 75.0),
            frequency_search_hz=(0.0, 2.0),
        )
        decoded = decode_deep_likelihoods(recovered.likelihoods, encoded.config)
        self.assertEqual(decoded.payload, payload)
        self.assertEqual(recovered.clock_error_ppm, 75.0)
        self.assertEqual(recovered.frequency_hypothesis_hz, 2.0)

    def test_waveform_occupied_bandwidth_is_below_project_limit(self) -> None:
        encoded = encode_deep_payload(b"Aurora Deep message!")
        bandwidth = occupied_bandwidth_hz(modulate_deep_audio(encoded.bits))
        self.assertGreater(bandwidth, DEEP_SYMBOL_RATE)
        self.assertLess(bandwidth, 1_000.0)

    def test_pilot_insertion_preserves_exact_data_order(self) -> None:
        data = bits_to_bpsk(([0, 1] * 80))
        multiplexed = multiplex_deep_pilots(data)
        self.assertEqual(deep_pilot_overhead(len(data)), 16)
        self.assertTrue(np.array_equal(multiplexed[:128], data[:128]))
        self.assertTrue(
            np.array_equal(multiplexed[128:144], deep_pilot_symbols())
        )
        self.assertTrue(np.array_equal(multiplexed[144:], data[128:]))

    def test_alternate_pilot_geometry_has_expected_overhead(self) -> None:
        data = bits_to_bpsk(([0, 1] * 80))
        multiplexed = multiplex_deep_pilots(
            data,
            interval=64,
            pilot_symbol_count=8,
        )
        self.assertEqual(deep_pilot_overhead(160, 64, 8), 16)
        self.assertEqual(len(multiplexed), 176)
        self.assertTrue(np.array_equal(multiplexed[:64], data[:64]))
        self.assertTrue(
            np.array_equal(multiplexed[64:72], deep_pilot_symbols(8))
        )

    def test_noise_only_input_is_not_acquired(self) -> None:
        encoded = encode_deep_payload(b"Aurora Deep message!")
        reference = modulate_deep_audio(encoded.bits)
        noise = AudioBuffer(
            np.random.default_rng(9)
            .normal(0.0, 1.0, reference.frame_count)
            .astype(np.float32),
            reference.sample_rate,
        )
        with self.assertRaisesRegex(ValueError, "acquisition failed"):
            recover_deep_likelihoods(noise, len(encoded.bits))

    def test_distributed_pilots_track_slow_carrier_drift(self) -> None:
        payload = b"Aurora Deep message!"
        encoded = encode_deep_payload(payload)
        clean = modulate_deep_audio(encoded.bits)
        samples = np.asarray(clean.samples, dtype=np.float64)
        spectrum = np.fft.fft(samples)
        multiplier = np.zeros(len(samples))
        multiplier[0] = 1.0
        multiplier[1 : len(samples) // 2] = 2.0
        multiplier[len(samples) // 2] = 1.0
        analytic = np.fft.ifft(spectrum * multiplier)
        time = np.arange(len(samples), dtype=np.float64) / clean.sample_rate
        phase = 2.0 * np.pi * (0.02 * time + 0.001 * time * time)
        drifting = AudioBuffer(
            np.real(analytic * np.exp(1j * phase)).astype(np.float32),
            clean.sample_rate,
        )
        recovered = recover_deep_likelihoods(
            drifting,
            len(encoded.bits),
            tracking_enabled=True,
        )
        decoded = decode_deep_likelihoods(recovered.likelihoods, encoded.config)
        self.assertEqual(decoded.payload, payload)
        self.assertGreater(recovered.pilot_quality, 0.5)

    def test_bounded_receiver_returns_unknown_timing_candidates(self) -> None:
        encoded = encode_deep_payload(b"Aurora Deep message!")
        audio = modulate_deep_audio(encoded.bits, leading_silence_samples=731)
        candidates = recover_deep_candidate_likelihoods(
            audio,
            len(encoded.bits),
            acquisition_peaks=2,
            decode_candidates=2,
        )
        self.assertGreaterEqual(len(candidates), 1)
        self.assertFalse(candidates[0].fading_equalization_enabled)
        self.assertGreaterEqual(candidates[0].channel_variation_confidence, 0.0)
        payloads = []
        for candidate in candidates:
            try:
                frame = decode_deep_likelihoods(
                    candidate.likelihoods, encoded.config
                )
            except ValueError:
                continue
            payloads.append(frame.payload)
        self.assertIn(b"Aurora Deep message!", payloads)

    def test_fading_activation_ratio_is_validated(self) -> None:
        encoded = encode_deep_payload(b"Aurora Deep message!")
        audio = modulate_deep_audio(encoded.bits)
        with self.assertRaisesRegex(ValueError, "activation gain ratio"):
            recover_deep_candidate_likelihoods(
                audio,
                len(encoded.bits),
                fading_activation_gain_ratio=1.1,
            )

    def test_fading_confidence_threshold_is_validated(self) -> None:
        encoded = encode_deep_payload(b"Aurora Deep message!")
        audio = modulate_deep_audio(encoded.bits)
        with self.assertRaisesRegex(ValueError, "confidence threshold"):
            recover_deep_candidate_likelihoods(
                audio,
                len(encoded.bits),
                fading_confidence_threshold=0.0,
            )

    def test_time_diverse_acquisition_recovers_clean_payload(self) -> None:
        payload = b"Aurora Deep message!"
        encoded = encode_deep_payload(payload)
        audio = modulate_deep_audio(
            encoded.bits,
            leading_silence_samples=731,
        )
        candidates = recover_deep_candidate_likelihoods(
            audio,
            len(encoded.bits),
            acquisition_diversity=True,
        )
        decoded = decode_deep_likelihoods(
            candidates[0].likelihoods,
            encoded.config,
        )
        self.assertEqual(decoded.payload, payload)


if __name__ == "__main__":
    unittest.main()
