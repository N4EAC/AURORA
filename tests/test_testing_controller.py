"""Tests for the Aurora simulation-only operator controller."""

import unittest

import numpy as np

from gui.testing_controller import (
    CHANNEL_PRESETS,
    CHANNEL_IMPAIRMENT_PROFILES,
    AWGN_IMPAIRMENTS,
    BenchmarkResult,
    ChannelImpairments,
    SweepConfig,
    TestingController,
    _fading_envelope,
    _impulse_mask,
    estimate_threshold_snr_db,
    snr_to_coded_ebn0_db,
    snr_to_esn0_db,
    wilson_interval,
)


class TestingControllerTests(unittest.TestCase):
    def test_synthetic_signal_has_expected_shape_and_diagnostics(self) -> None:
        controller = TestingController(sample_rate=12_000, block_size=512)
        samples, diagnostics = controller.generate_samples()
        self.assertEqual(samples.shape, (512,))
        self.assertEqual(samples.dtype, np.float32)
        self.assertTrue(diagnostics.synchronized)
        self.assertEqual(diagnostics.crc_status, "WAITING")
        self.assertGreater(float(np.max(np.abs(samples))), 0.1)

    def test_qpsk_local_round_trip(self) -> None:
        result = TestingController().local_round_trip("Aurora test", "QPSK")
        self.assertEqual(result.received_text, "Aurora test")
        self.assertEqual(result.modulation, "QPSK")
        self.assertEqual(result.diagnostics.crc_status, "PASS")

    def test_bpsk_local_round_trip(self) -> None:
        result = TestingController().local_round_trip("weak signal", "BPSK")
        self.assertEqual(result.received_text, "weak signal")
        self.assertEqual(result.modulation, "BPSK")

    def test_empty_message_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Enter a message"):
            TestingController().local_round_trip("   ", "QPSK")

    def test_clean_channel_recovers_one_hundred_frames(self) -> None:
        preset = CHANNEL_PRESETS["Clean"]
        result = TestingController().run_benchmark(
            "Aurora",
            "QPSK",
            snr_db=preset.snr_db,
            frequency_offset_hz=preset.frequency_offset_hz,
            frame_count=100,
            preset_name=preset.name,
        )
        self.assertEqual(result.successful_frames, 100)
        self.assertEqual(result.failed_frames, 0)
        self.assertEqual(result.success_rate, 100.0)

    def test_weak_and_severe_presets_show_degradation(self) -> None:
        controller = TestingController()
        weak = CHANNEL_PRESETS["Weak Signal"]
        severe = CHANNEL_PRESETS["Severe"]
        weak_result = controller.run_benchmark(
            "Aurora",
            "QPSK",
            snr_db=weak.snr_db,
            frequency_offset_hz=weak.frequency_offset_hz,
            frame_count=30,
            preset_name=weak.name,
        )
        severe_result = controller.run_benchmark(
            "Aurora",
            "QPSK",
            snr_db=severe.snr_db,
            frequency_offset_hz=severe.frequency_offset_hz,
            frame_count=30,
            preset_name=severe.name,
        )
        self.assertGreater(weak_result.successful_frames, severe_result.successful_frames)
        self.assertGreater(severe_result.channel_bit_errors, weak_result.channel_bit_errors)

    def test_benchmark_is_reproducible(self) -> None:
        controller = TestingController()
        arguments = {
            "snr_db": 2.0,
            "frequency_offset_hz": 0.1,
            "frame_count": 10,
            "seed": 44,
        }
        first = controller.run_benchmark("repeat", "BPSK", **arguments)
        second = controller.run_benchmark("repeat", "BPSK", **arguments)
        self.assertEqual(first.successful_frames, second.successful_frames)
        self.assertEqual(first.channel_bit_errors, second.channel_bit_errors)
        self.assertEqual(first.corrected_bit_errors, second.corrected_bit_errors)

    def test_explicit_awgn_preserves_baseline_results(self) -> None:
        arguments = {
            "snr_db": -5.0,
            "frequency_offset_hz": 0.0,
            "frame_count": 12,
            "seed": 91,
        }
        controller = TestingController()
        default = controller.run_benchmark("baseline", "BPSK", **arguments)
        explicit = controller.run_benchmark(
            "baseline", "BPSK", impairments=AWGN_IMPAIRMENTS, **arguments
        )
        self.assertEqual(default.successful_frames, explicit.successful_frames)
        self.assertEqual(default.channel_bit_errors, explicit.channel_bit_errors)

    def test_interleaved_benchmark_is_reproducible(self) -> None:
        arguments = {
            "snr_db": -18.0,
            "frequency_offset_hz": 0.0,
            "frame_count": 12,
            "seed": 73,
            "symbol_rate": 31.25,
            "reference_bandwidth_hz": 2_500.0,
            "interleaver_columns": 16,
        }
        controller = TestingController()
        first = controller.run_benchmark("interleaved", "BPSK", **arguments)
        second = controller.run_benchmark("interleaved", "BPSK", **arguments)
        self.assertEqual(first.successful_frames, second.successful_frames)
        self.assertEqual(first.channel_bit_errors, second.channel_bit_errors)
        self.assertEqual(first.interleaver_columns, 16)

    def test_sweep_preserves_interleaver_geometry(self) -> None:
        config = SweepConfig(
            start_snr_db=-18.0,
            stop_snr_db=-18.0,
            frames_per_point=8,
            seeds=(1,),
            interleaver_columns=16,
        )
        result = TestingController().run_snr_sweep("geometry", "BPSK", config)
        self.assertEqual(result.config.interleaver_columns, 16)
        self.assertEqual(result.points[0].interleaver_columns, 16)

    def test_each_hf_impairment_changes_symbols_deterministically(self) -> None:
        symbols = np.ones(64, dtype=np.complex128)
        cases = (
            ChannelImpairments(name="fading", fading_depth=0.4, fading_cycles_per_frame=1.0),
            ChannelImpairments(name="multipath", multipath_delay_symbols=2, multipath_gain=0.3),
            ChannelImpairments(name="impulses", impulse_probability=1.0, impulse_scale=3.0),
            ChannelImpairments(name="phase", phase_drift_radians=0.8),
            ChannelImpairments(name="timing", timing_offset_symbols=0.25),
        )
        baseline, _ = TestingController._impair_symbols(
            symbols, 20.0, 0.0, 31.25, np.random.default_rng(5)
        )
        for impairments in cases:
            with self.subTest(profile=impairments.name):
                first, _ = TestingController._impair_symbols(
                    symbols,
                    20.0,
                    0.0,
                    31.25,
                    np.random.default_rng(5),
                    impairments,
                )
                second, _ = TestingController._impair_symbols(
                    symbols,
                    20.0,
                    0.0,
                    31.25,
                    np.random.default_rng(5),
                    impairments,
                )
                self.assertTrue(np.array_equal(first, second))
                self.assertFalse(np.array_equal(first, baseline))

    def test_fading_phase_varies_per_frame_and_replays_from_seed(self) -> None:
        fading = CHANNEL_IMPAIRMENT_PROFILES["Fading only"]
        first_random = np.random.default_rng(2026)
        first_frame = _fading_envelope(128, fading, first_random)
        second_frame = _fading_envelope(128, fading, first_random)

        replay_random = np.random.default_rng(2026)
        replay_first = _fading_envelope(128, fading, replay_random)
        replay_second = _fading_envelope(128, fading, replay_random)

        self.assertFalse(np.array_equal(first_frame, second_frame))
        self.assertTrue(np.array_equal(first_frame, replay_first))
        self.assertTrue(np.array_equal(second_frame, replay_second))

    def test_impulse_bursts_expand_seeded_starts_contiguously(self) -> None:
        seed = 88
        length = 200
        probability = 0.02
        burst_symbols = 5
        actual = _impulse_mask(
            length,
            probability,
            burst_symbols,
            np.random.default_rng(seed),
        )

        starts = np.random.default_rng(seed).random(length) < probability
        expected = starts.copy()
        for offset in range(1, burst_symbols):
            expected[offset:] |= starts[:-offset]

        self.assertTrue(np.array_equal(actual, expected))
        self.assertGreater(np.count_nonzero(actual), np.count_nonzero(starts))

    def test_single_symbol_impulse_mask_preserves_existing_behavior(self) -> None:
        seed = 99
        expected = np.random.default_rng(seed).random(64) < 0.1
        actual = _impulse_mask(64, 0.1, 1, np.random.default_rng(seed))
        self.assertTrue(np.array_equal(actual, expected))

    def test_severe_hf_profile_degrades_awgn_baseline(self) -> None:
        arguments = {
            "snr_db": -19.0,
            "frequency_offset_hz": 0.0,
            "frame_count": 20,
            "seed": 7,
            "symbol_rate": 31.25,
            "reference_bandwidth_hz": 2_500.0,
        }
        controller = TestingController()
        awgn = controller.run_benchmark(
            "profile", "BPSK", impairments=CHANNEL_IMPAIRMENT_PROFILES["AWGN only"], **arguments
        )
        severe = controller.run_benchmark(
            "profile",
            "BPSK",
            impairments=CHANNEL_IMPAIRMENT_PROFILES["Severe HF simulation"],
            **arguments,
        )
        self.assertLess(severe.successful_frames, awgn.successful_frames)
        self.assertGreater(severe.channel_bit_errors, awgn.channel_bit_errors)

    def test_attribution_profiles_isolate_one_impairment(self) -> None:
        isolated_fields = {
            "Fading only": ("fading_depth", "fading_cycles_per_frame"),
            "Multipath only": ("multipath_delay_symbols", "multipath_gain"),
            "Impulsive noise only": ("impulse_probability", "impulse_scale"),
            "Phase drift only": ("phase_drift_radians",),
            "Timing offset only": ("timing_offset_symbols",),
        }
        numeric_fields = (
            "fading_depth",
            "fading_cycles_per_frame",
            "multipath_delay_symbols",
            "multipath_gain",
            "impulse_probability",
            "impulse_scale",
            "impulse_burst_symbols",
            "phase_drift_radians",
            "timing_offset_symbols",
        )
        for profile_name, active_fields in isolated_fields.items():
            with self.subTest(profile=profile_name):
                profile = CHANNEL_IMPAIRMENT_PROFILES[profile_name]
                for field_name in numeric_fields:
                    value = getattr(profile, field_name)
                    if field_name == "impulse_burst_symbols":
                        expected = 1
                        self.assertEqual(value, expected)
                    elif field_name in active_fields:
                        self.assertGreater(value, 0)
                    else:
                        self.assertEqual(value, 0)

    def test_minus_twenty_two_db_conversion_includes_processing_gain(self) -> None:
        converted = snr_to_esn0_db(-22.0, 2_500.0, 31.25)
        self.assertAlmostEqual(converted, -2.9691, places=3)

    def test_coded_ebn0_accounts_for_bits_per_symbol(self) -> None:
        bpsk = snr_to_coded_ebn0_db(-22.0, 2_500.0, 31.25, "BPSK")
        qpsk = snr_to_coded_ebn0_db(-22.0, 2_500.0, 31.25, "QPSK")
        self.assertAlmostEqual(bpsk, -2.9691, places=3)
        self.assertAlmostEqual(qpsk, -5.9794, places=3)

    def test_threshold_is_interpolated_only_when_bracketed(self) -> None:
        def point(snr_db: float, successes: int) -> BenchmarkResult:
            return BenchmarkResult(
                preset_name="Sweep",
                modulation="BPSK",
                snr_db=snr_db,
                frequency_offset_hz=0.0,
                frame_count=100,
                successful_frames=successes,
                channel_bit_errors=0,
                corrected_bit_errors=0,
                elapsed_seconds=1.0,
            )

        points = (point(-21.0, 40), point(-20.0, 60), point(-19.0, 80))
        self.assertAlmostEqual(estimate_threshold_snr_db(points, 50.0), -20.5)
        self.assertIsNone(estimate_threshold_snr_db(points, 90.0))

    def test_wilson_interval_bounds_perfect_result(self) -> None:
        lower, upper = wilson_interval(100, 100)
        self.assertGreater(lower, 96.0)
        self.assertEqual(upper, 100.0)

    def test_snr_sweep_is_ordered_and_reproducible(self) -> None:
        config = SweepConfig(
            start_snr_db=-6.0,
            stop_snr_db=6.0,
            step_snr_db=6.0,
            frames_per_point=24,
            seeds=(10, 11),
            reference_bandwidth_hz=2_500.0,
            symbol_rate=2_500.0,
        )
        controller = TestingController()
        first = controller.run_snr_sweep("sweep", "BPSK", config)
        second = controller.run_snr_sweep("sweep", "BPSK", config)
        self.assertEqual([point.snr_db for point in first.points], [-6.0, 0.0, 6.0])
        self.assertEqual(
            [point.successful_frames for point in first.points],
            [point.successful_frames for point in second.points],
        )
        successes = [point.successful_frames for point in first.points]
        self.assertEqual(successes, sorted(successes))

    def test_snr_sweep_can_be_cancelled_between_frames(self) -> None:
        config = SweepConfig(
            start_snr_db=-10.0,
            stop_snr_db=10.0,
            step_snr_db=2.0,
            frames_per_point=100,
            seeds=(1,),
        )
        checks = 0

        def should_continue() -> bool:
            nonlocal checks
            checks += 1
            return checks <= 5

        result = TestingController().run_snr_sweep(
            "cancel", "QPSK", config, should_continue=should_continue
        )
        self.assertTrue(result.cancelled)
        self.assertLess(result.points[0].frame_count, config.frames_per_point)


if __name__ == "__main__":
    unittest.main()
