"""Tests for Aurora's bounded OFDM bandwidth controller."""

import unittest

from modem.bandwidth_adaptation import (
    ChannelConditions,
    fixed_bandwidth,
    select_bandwidth,
)


class BandwidthAdaptationTests(unittest.TestCase):
    def test_missing_or_low_confidence_measurements_use_500_hz(self) -> None:
        self.assertEqual(select_bandwidth(ChannelConditions()).bandwidth_hz, 500)
        complete = ChannelConditions(
            snr_db=20.0,
            interference_ratio=0.0,
            fading_depth=0.0,
            multipath_delay_ms=0.0,
            frequency_error_hz=0.0,
            available_audio_passband_hz=2_800.0,
            confidence=0.69,
        )
        self.assertEqual(select_bandwidth(complete).bandwidth_hz, 500)

    def test_clean_stable_channel_selects_2800_hz(self) -> None:
        decision = select_bandwidth(
            ChannelConditions(
                snr_db=18.0,
                interference_ratio=0.05,
                fading_depth=0.10,
                multipath_delay_ms=1.0,
                frequency_error_hz=0.3,
                available_audio_passband_hz=3_000.0,
                confidence=0.95,
            )
        )
        self.assertEqual(decision.bandwidth_hz, 2_800)

    def test_moderate_channel_selects_2300_hz(self) -> None:
        decision = select_bandwidth(
            ChannelConditions(
                snr_db=7.0,
                interference_ratio=0.20,
                fading_depth=0.30,
                multipath_delay_ms=5.0,
                frequency_error_hz=2.0,
                available_audio_passband_hz=2_500.0,
                confidence=0.85,
            )
        )
        self.assertEqual(decision.bandwidth_hz, 2_300)

    def test_impairment_or_narrow_passband_selects_500_hz(self) -> None:
        decision = select_bandwidth(
            ChannelConditions(
                snr_db=15.0,
                interference_ratio=0.50,
                fading_depth=0.10,
                multipath_delay_ms=1.0,
                frequency_error_hz=0.2,
                available_audio_passband_hz=2_000.0,
                confidence=0.90,
            )
        )
        self.assertEqual(decision.bandwidth_hz, 500)

    def test_fixed_profile_is_not_automatic(self) -> None:
        decision = fixed_bandwidth(2_300)
        self.assertFalse(decision.automatic)
        self.assertEqual(decision.bandwidth_hz, 2_300)


if __name__ == "__main__":
    unittest.main()
