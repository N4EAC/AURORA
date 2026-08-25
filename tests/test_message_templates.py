"""Tests for operator canned-message tokens."""

from datetime import datetime, timezone
import unittest

from modem.message_templates import expand_message_template


class MessageTemplateTests(unittest.TestCase):
    def test_station_and_time_tokens_expand(self) -> None:
        expanded = expand_message_template(
            "<NAME> <CALL> at <TIME>",
            name="Eduardo",
            callsign="n4eac",
            now=datetime(2026, 8, 25, 14, 7, tzinfo=timezone.utc),
        )
        self.assertEqual(expanded, "Eduardo N4EAC at 14:07 UTC")


if __name__ == "__main__":
    unittest.main()
