"""Tests for the Aurora Deep payload feasibility runner."""

import unittest

from dsp.audio_channel import AudioChannelConfig
from dsp.deep_codec import DeepCodecConfig
from modem.deep_mode_study import (
    DEEP_CHANNEL_PROFILES,
    DeepCandidate,
    DeepChannelProfile,
    DeepStudyConfig,
    run_deep_mode_study,
)


FAST_CANDIDATE = DeepCandidate("test rate-1/4", DeepCodecConfig(2, 16))
NATIVE_CANDIDATE = DeepCandidate(
    "test native rate-1/4",
    DeepCodecConfig(1, 16, "native_rate_quarter"),
)


class DeepModeStudyTests(unittest.TestCase):
    def test_study_decodes_payload_and_reports_non_protocol_status(self) -> None:
        events: list[tuple[str, dict[str, object]]] = []
        result = run_deep_mode_study(
            DeepStudyConfig(
                snr_points_db=(20.0,),
                seeds=(11,),
                noise_trials=1,
                candidates=(FAST_CANDIDATE,),
                frequency_offset_hz=0.0,
                frequency_search_hz=(0.0,),
                clock_search_ppm=(0.0,),
            ),
            event_callback=lambda event, fields: events.append((event, fields)),
        )
        self.assertFalse(result.over_the_air_protocol)
        self.assertEqual(result.measurement_domain, "deep_payload_research")
        point = result.points[0]
        self.assertEqual(point.trials, 1)
        self.assertEqual(point.decoded, 1)
        self.assertEqual(point.false_decodes, 0)
        self.assertGreater(point.duration_seconds, 30.0)
        self.assertLess(point.duration_seconds, 40.0)
        self.assertAlmostEqual(
            point.information_rate_bps,
            160.0 / point.duration_seconds,
        )
        self.assertEqual(events[0][0], "DEEP_STUDY_START")
        self.assertFalse(events[0][1]["over_the_air_protocol"])
        self.assertEqual(events[-1][0], "DEEP_STUDY_END")
        self.assertEqual(
            [point.tracking_enabled for point in result.points],
            [False, True],
        )

    def test_cancellation_occurs_between_trials(self) -> None:
        checks = 0

        def should_continue() -> bool:
            nonlocal checks
            checks += 1
            return checks == 1

        result = run_deep_mode_study(
            DeepStudyConfig(
                snr_points_db=(20.0,),
                seeds=(1, 2),
                noise_trials=1,
                candidates=(FAST_CANDIDATE,),
                frequency_offset_hz=0.0,
                frequency_search_hz=(0.0,),
                clock_search_ppm=(0.0,),
            ),
            should_continue=should_continue,
        )
        self.assertTrue(result.cancelled)
        self.assertEqual(result.points[0].trials, 1)
        self.assertEqual(result.points[0].noise_trials, 0)

    def test_named_profiles_isolate_expected_impairments(self) -> None:
        self.assertEqual(
            DEEP_CHANNEL_PROFILES["Clock error only"].channel.clock_error_ppm,
            75.0,
        )
        self.assertGreater(
            DEEP_CHANNEL_PROFILES["Multipath only"].channel.multipath_gain,
            0.0,
        )
        isolated = DeepChannelProfile(
            "Test", AudioChannelConfig(snr_db=None, timing_offset_samples=0.2)
        )
        self.assertEqual(isolated.channel.timing_offset_samples, 0.2)

    def test_reference_payload_must_be_exactly_twenty_bytes(self) -> None:
        with self.assertRaisesRegex(ValueError, "20 bytes"):
            DeepStudyConfig(payload=b"short")

    def test_tracking_improves_seeded_weak_signal_result(self) -> None:
        result = run_deep_mode_study(
            DeepStudyConfig(
                snr_points_db=(-18.0,),
                seeds=(2026,),
                noise_trials=0,
                candidates=(FAST_CANDIDATE,),
                frequency_offset_hz=0.0,
                frequency_search_hz=(0.0,),
                clock_search_ppm=(0.0,),
                tracking_options=(False, True),
            )
        )
        disabled, enabled = result.points
        self.assertEqual(disabled.decoded, 0)
        self.assertEqual(enabled.decoded, 1)
        self.assertGreaterEqual(enabled.decoded, disabled.decoded)

    def test_low_pilot_quality_is_classified_after_acquisition(self) -> None:
        result = run_deep_mode_study(
            DeepStudyConfig(
                snr_points_db=(20.0,),
                seeds=(2,),
                noise_trials=0,
                candidates=(FAST_CANDIDATE,),
                frequency_offset_hz=0.0,
                frequency_search_hz=(0.0,),
                clock_search_ppm=(0.0,),
                tracking_options=(True,),
                minimum_pilot_quality=1_000_000.0,
            )
        )
        point = result.points[0]
        self.assertEqual(point.acquired, 1)
        self.assertEqual(point.carrier_tracking_failures, 1)

    def test_native_candidate_uses_identical_airtime_and_channel_trials(self) -> None:
        result = run_deep_mode_study(
            DeepStudyConfig(
                snr_points_db=(-18.0,),
                seeds=(2026,),
                noise_trials=0,
                candidates=(FAST_CANDIDATE, NATIVE_CANDIDATE),
                frequency_offset_hz=0.0,
                frequency_search_hz=(0.0,),
                clock_search_ppm=(0.0,),
                tracking_options=(True,),
            )
        )
        repeated, native = result.points
        self.assertEqual(repeated.trials, native.trials)
        self.assertEqual(repeated.duration_seconds, native.duration_seconds)
        self.assertGreaterEqual(native.decoded, repeated.decoded)


if __name__ == "__main__":
    unittest.main()
