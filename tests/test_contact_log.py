"""Tests for Aurora contact persistence."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from radio.contact_log import ContactLog, ContactRecord


class ContactLogTests(unittest.TestCase):
    def test_contact_is_persisted_and_normalized(self) -> None:
        logged_at = datetime(2026, 7, 21, 20, 30, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            contact_log = ContactLog(Path(directory) / "contacts.sqlite3")
            stored = contact_log.add(
                ContactRecord(
                    " k1abc ",
                    14_074_000,
                    sent_report="-08",
                    received_report="-11",
                    logged_at=logged_at,
                )
            )
            recent = contact_log.recent()

        self.assertIsNotNone(stored.database_id)
        self.assertEqual(recent[0].callsign, "K1ABC")
        self.assertEqual(recent[0].logged_at, logged_at)
        self.assertEqual(recent[0].frequency_hz, 14_074_000)

    def test_empty_callsign_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "callsign"):
            ContactRecord("  ", 7_100_000)


if __name__ == "__main__":
    unittest.main()
