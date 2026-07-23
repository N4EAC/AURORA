"""Tests for the non-protocol Aurora extreme acquisition study."""

import unittest

from modem.extreme_mode_study import (
    EXTREME_CHANNEL_PROFILES,
    ExtremeChannelProfile,
    ExtremeStudyConfig,
    IdealCodeBudget,
    awgn_capacity_bps,
    information_ebn0_db,
    run_extreme_study,
    run_clock_ppm_sweep,
)
from dsp.audio_channel import AudioChannelConfig


class ExtremeModeStudyTests(unittest.TestCase):
    def test_minus_thirty_db_capacity_and_ideal_budget_are_consistent(self) -> None:
        budget = IdealCodeBudget()
        self.assertAlmostEqual(awgn_capacity_bps(2_500.0, -30.0), 3.60494, places=4)
        self.assertEqual(budget.rate, 0.125)
        self.assertAlmostEqual(budget.information_rate_bps, 0.9765625)
        self.assertLess(budget.information_rate_bps, awgn_capacity_bps(2_500.0, -30.0))
        self.assertAlmostEqual(
            information_ebn0_db(-30.0, 2_500.0, budget.information_rate_bps),
            4.0824,
            places=3,
        )

    def test_study_reports_acquisition_without_payload_claims(self) -> None:
        events: list[tuple[str, dict[str, object]]] = []
        result = run_extreme_study(
            ExtremeStudyConfig(
                snr_db=10.0,
                seeds=(5,),
                noise_trials=1,
                frequency_search_hz=(0.0,),
                detection_peak_to_median=5.0,
            ),
            event_callback=lambda event, fields: events.append((event, fields)),
        )
        self.assertEqual(result.measurement_domain, "extreme_research")
        self.assertEqual({item.modulation for item in result.results}, {"BPSK", "4GFSK"})
        self.assertTrue(all(item.detected_trials == 1 for item in result.results))
        self.assertTrue(all(item.timing_located_trials == 1 for item in result.results))
        self.assertTrue(all(item.frequency_matched_trials == 1 for item in result.results))
        self.assertTrue(all(item.clock_matched_trials == 1 for item in result.results))
        self.assertTrue(all(item.acquired_trials == 1 for item in result.results))
        self.assertTrue(all(item.false_alarms == 0 for item in result.results))
        self.assertTrue(
            all(item.mean_absolute_timing_error_samples < 0.1 for item in result.results)
        )
        start = next(fields for event, fields in events if event == "EXTREME_STUDY_START")
        self.assertFalse(start["ideal_code_implemented"])
        candidates = [fields for event, fields in events if event == "EXTREME_STUDY_CANDIDATE"]
        self.assertTrue(all(not fields["payload_decode_attempted"] for fields in candidates))
        end = next(fields for event, fields in events if event == "EXTREME_STUDY_END")
        self.assertFalse(end["over_the_air_protocol"])

    def test_profiles_isolate_named_impairments(self) -> None:
        isolated = {
            "Fading only": ("fading_depth", "fading_cycles_per_frame"),
            "Multipath only": ("multipath_delay_ms", "multipath_gain"),
            "Clock error only": ("clock_error_ppm",),
            "Impulsive noise only": ("impulse_probability", "impulse_scale"),
        }
        fields = (
            "timing_offset_samples",
            "clock_error_ppm",
            "multipath_delay_ms",
            "multipath_gain",
            "fading_depth",
            "fading_cycles_per_frame",
            "impulse_probability",
            "impulse_scale",
        )
        for profile_name, active in isolated.items():
            with self.subTest(profile=profile_name):
                channel = EXTREME_CHANNEL_PROFILES[profile_name].channel
                for field in fields:
                    value = getattr(channel, field)
                    if field in active:
                        self.assertNotEqual(value, 0.0)
                    else:
                        self.assertEqual(value, 0.0)

    def test_study_cancellation_reports_completed_trials_only(self) -> None:
        checks = 0

        def should_continue() -> bool:
            nonlocal checks
            checks += 1
            return checks == 1

        result = run_extreme_study(
            ExtremeStudyConfig(
                snr_db=10.0,
                seeds=(1, 2),
                noise_trials=2,
                modulations=("4gfsk",),
                frequency_search_hz=(0.0,),
            ),
            should_continue=should_continue,
        )
        self.assertTrue(result.cancelled)
        candidate = result.results[0]
        self.assertEqual(candidate.trials, 1)
        self.assertEqual(candidate.noise_trials, 0)
        self.assertEqual(candidate.false_alarm_confidence_95, (0.0, 0.0))

    def test_clock_sweep_selects_injected_grid_points(self) -> None:
        config = ExtremeStudyConfig(
            snr_db=10.0,
            seeds=(3,),
            noise_trials=1,
            modulations=("4gfsk",),
            frequency_search_hz=(0.0,),
            clock_search_ppm=(0.0, 75.0),
            profile=ExtremeChannelProfile(
                "Clock test",
                AudioChannelConfig(snr_db=None),
            ),
        )
        sweep = run_clock_ppm_sweep(config, (0.0, 75.0))
        self.assertFalse(sweep.cancelled)
        self.assertEqual(
            [point.injected_clock_error_ppm for point in sweep.points],
            [0.0, 75.0],
        )
        self.assertTrue(
            all(point.result.clock_matched_trials == 1 for point in sweep.points)
        )
        self.assertTrue(
            all(point.result.acquired_trials == 1 for point in sweep.points)
        )

    def test_study_reports_clock_error_outside_search_grid(self) -> None:
        result = run_extreme_study(
            ExtremeStudyConfig(
                snr_db=10.0,
                seeds=(4,),
                noise_trials=1,
                modulations=("4gfsk",),
                frequency_search_hz=(0.0,),
                clock_search_ppm=(0.0,),
                profile=ExtremeChannelProfile(
                    "Unresolved clock",
                    AudioChannelConfig(snr_db=None, clock_error_ppm=75.0),
                ),
            )
        )
        candidate = result.results[0]
        self.assertEqual(candidate.clock_matched_trials, 0)
        self.assertEqual(candidate.mean_clock_error_ppm, 0.0)
        self.assertEqual(candidate.mean_absolute_clock_error_ppm, 75.0)
        self.assertEqual(candidate.acquired_trials, 0)


if __name__ == "__main__":
    unittest.main()
