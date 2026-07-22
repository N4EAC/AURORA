"""Tests for Aurora structured session debug logging."""

from pathlib import Path
import tempfile
import threading
import unittest

from util.session_debug_log import SessionDebugLog


class SessionDebugLogTests(unittest.TestCase):
    def test_session_events_are_flushed_and_structured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session_log = SessionDebugLog(directory, "0.1.0-test")
            session_log.record(
                "channel_test_result",
                successful_frames=95,
                frame_count=100,
                message_length=12,
            )
            content_before_close = session_log.path.read_text(encoding="utf-8")
            path = session_log.path
            session_log.close()
            content_after_close = path.read_text(encoding="utf-8")

        self.assertIn("SESSION_START", content_before_close)
        self.assertIn("CHANNEL_TEST_RESULT", content_before_close)
        self.assertIn("successful_frames=95", content_before_close)
        self.assertIn("SESSION_END", content_after_close)

    def test_concurrent_events_are_not_interleaved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session_log = SessionDebugLog(Path(directory), "0.1.0-test")

            def writer(worker: int) -> None:
                for sequence in range(10):
                    session_log.record("WORKER_EVENT", worker=worker, sequence=sequence)

            threads = [threading.Thread(target=writer, args=(index,)) for index in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            path = session_log.path
            session_log.close()
            lines = path.read_text(encoding="utf-8").splitlines()

        worker_lines = [line for line in lines if "WORKER_EVENT" in line]
        self.assertEqual(len(worker_lines), 40)
        self.assertTrue(all(line.count("WORKER_EVENT") == 1 for line in worker_lines))

    def test_robustness_sweep_point_is_immediately_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session_log = SessionDebugLog(directory, "0.1.0-test")
            session_log.record(
                "ROBUSTNESS_SWEEP_POINT",
                snr_db=-22.0,
                esn0_db=-2.969,
                frame_count=200,
                success_rate_percent=42.0,
            )
            content = session_log.path.read_text(encoding="utf-8")
            session_log.close()

        self.assertIn("ROBUSTNESS_SWEEP_POINT", content)
        self.assertIn("snr_db=-22.0", content)
        self.assertIn("frame_count=200", content)

    def test_profile_threshold_comparison_is_structured(self) -> None:
        thresholds = {
            "AWGN only": {"threshold_50_percent_snr_db": -21.0},
            "Fading only": {"threshold_50_percent_snr_db": -18.5},
        }
        with tempfile.TemporaryDirectory() as directory:
            session_log = SessionDebugLog(directory, "0.1.0-test")
            session_log.record(
                "ROBUSTNESS_PROFILE_COMPARISON",
                modulation="BPSK",
                thresholds_by_profile=thresholds,
            )
            content = session_log.path.read_text(encoding="utf-8")
            session_log.close()

        self.assertIn("ROBUSTNESS_PROFILE_COMPARISON", content)
        self.assertIn('"AWGN only"', content)
        self.assertIn('"Fading only"', content)


if __name__ == "__main__":
    unittest.main()
