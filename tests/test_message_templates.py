"""Tests for operator canned-message tokens."""

from datetime import datetime, timezone
import unittest

from modem.message_templates import (
    CANNED_MESSAGES,
    expand_message_template,
    prepare_message_template,
)


class MessageTemplateTests(unittest.TestCase):
    def test_station_and_time_tokens_expand(self) -> None:
        expanded = expand_message_template(
            "<NAME> <CALL> at <TIME>",
            name="Eduardo",
            callsign="n4eac",
            now=datetime(2026, 8, 25, 14, 7, tzinfo=timezone.utc),
        )
        self.assertEqual(expanded, "Eduardo N4EAC at 14:07 UTC")

    def test_target_tokens_and_bty_control_are_separated(self) -> None:
        prepared = prepare_message_template(
            "Hello <TNAME>, <TCALL> de <CALL>. <BTY>",
            name="Eduardo",
            callsign="N4EAC",
            target_callsign="W1AW",
            target_name="Joe",
        )
        self.assertEqual(prepared.text, "Hello Joe, W1AW de N4EAC.")
        self.assertTrue(prepared.back_to_you)
        self.assertNotIn("<BTY>", prepared.text)

    def test_target_token_requires_selected_station(self) -> None:
        with self.assertRaisesRegex(ValueError, "target station"):
            prepare_message_template(
                "Hello <TCALL>", name="Eduardo", callsign="N4EAC"
            )

    def test_bty_and_eoc_are_mutually_exclusive(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot"):
            prepare_message_template(
                "Done <BTY> <EOC>", name="Eduardo", callsign="N4EAC"
            )

    def test_split_token_uses_configured_reply_frequency(self) -> None:
        prepared = prepare_message_template(
            CANNED_MESSAGES["CQ Reply"],
            name="Eduardo",
            callsign="N4EAC",
            split_frequency_hz=7_114_000,
        )
        self.assertEqual(prepared.text, "CQ CQ de N4EAC listening on 7.114 MHz")

    def test_split_token_requires_armed_or_accepted_reply_channel(self) -> None:
        with self.assertRaisesRegex(ValueError, "Reply Channel"):
            prepare_message_template(
                "Listening on <SPLT>", name="Eduardo", callsign="N4EAC"
            )


if __name__ == "__main__":
    unittest.main()
