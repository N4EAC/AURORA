"""Tests for Aurora's offline audio-domain robustness harness."""

import tempfile
import unittest

from dsp.audio_channel import AudioChannelConfig
from modem.audio_robustness import (
    AudioBenchmarkConfig,
    AudioSweepConfig,
    run_audio_benchmark,
    run_audio_snr_sweep,
)
from util.session_debug_log import SessionDebugLog


class AudioRobustnessTests(unittest.TestCase):
    def test_clean_audio_benchmark_decodes_and_reports_domain(self) -> None:
        result = run_audio_benchmark(
            "clean",
            AudioBenchmarkConfig(
                frame_count=1,
                channel=AudioChannelConfig(snr_db=None),
            ),
        )
        self.assertEqual(result.frame_count, 1)
        self.assertEqual(result.synchronized_frames, 1)
        self.assertEqual(result.successful_frames, 1)
        self.assertEqual(result.measurement_domain, "audio_sim")
        self.assertGreater(result.occupied_bandwidth_hz, 0.0)

    def test_benchmark_is_seeded_and_emits_structured_events(self) -> None:
        events: list[tuple[str, dict[str, object]]] = []
        config = AudioBenchmarkConfig(
            frame_count=1,
            seed=77,
            frequency_offset_hz=0.05,
            channel=AudioChannelConfig(snr_db=10.0),
        )
        first = run_audio_benchmark(
            "repeat", config, event_callback=lambda event, fields: events.append((event, fields))
        )
        second = run_audio_benchmark("repeat", config)
        self.assertEqual(first.successful_frames, second.successful_frames)
        self.assertEqual(first.synchronized_frames, second.synchronized_frames)
        self.assertEqual([event for event, _ in events], ["AUDIO_ROBUSTNESS_START", "AUDIO_ROBUSTNESS_END"])
        self.assertTrue(all(fields["measurement_domain"] == "audio_sim" for _, fields in events))

    def test_benchmark_can_cancel_before_first_frame(self) -> None:
        result = run_audio_benchmark(
            "cancel",
            AudioBenchmarkConfig(frame_count=2),
            should_continue=lambda: False,
        )
        self.assertTrue(result.cancelled)
        self.assertEqual(result.frame_count, 0)

    def test_benchmark_events_can_be_written_to_session_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with SessionDebugLog(directory, "0.4.0-test") as session_log:
                run_audio_benchmark(
                    "logged",
                    AudioBenchmarkConfig(
                        frame_count=1,
                        channel=AudioChannelConfig(snr_db=None),
                    ),
                    event_callback=lambda event, fields: session_log.record(
                        event, **fields
                    ),
                )
                content = session_log.path.read_text(encoding="utf-8")
        self.assertIn("AUDIO_ROBUSTNESS_START", content)
        self.assertIn("AUDIO_ROBUSTNESS_END", content)
        self.assertIn('measurement_domain="audio_sim"', content)

    def test_small_sweep_is_ordered_and_reports_points(self) -> None:
        events: list[str] = []
        result = run_audio_snr_sweep(
            "sweep",
            AudioSweepConfig(
                start_snr_db=10.0,
                stop_snr_db=15.0,
                step_snr_db=5.0,
                frames_per_point=1,
                seeds=(9,),
                benchmark=AudioBenchmarkConfig(frame_count=1),
            ),
            event_callback=lambda event, fields: events.append(event),
        )
        self.assertEqual([snr for snr, _ in result.points], [10.0, 15.0])
        self.assertEqual(events.count("AUDIO_ROBUSTNESS_POINT"), 2)
        self.assertFalse(result.cancelled)


if __name__ == "__main__":
    unittest.main()
