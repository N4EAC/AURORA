"""Tests for connectionless Reply Channel contact state."""

import unittest

from modem.contact_session import ContactManager, TurnState, validate_reply_frequency


class ContactSessionTests(unittest.TestCase):
    def test_caller_offer_uses_complementary_tx_and_rx(self) -> None:
        manager = ContactManager()
        contact = manager.offer(
            local_callsign="N4EAC",
            normal_frequency_hz=7_117_000,
            reply_frequency_hz=7_107_000,
            mode="USB-D",
        )
        self.assertEqual(contact.transmit_frequency_hz, 7_117_000)
        self.assertEqual(contact.receive_frequency_hz, 7_107_000)
        self.assertNotEqual(contact.contact_id, 0)

    def test_responder_accepts_inverse_route(self) -> None:
        manager = ContactManager()
        contact = manager.accept(
            peer_callsign="W1AW",
            peer_name="Joe",
            contact_id=42,
            received_frequency_hz=7_117_000,
            reply_frequency_hz=7_107_000,
            normal_frequency_hz=7_117_000,
            mode="USB-D",
            window_seconds=120,
        )
        self.assertEqual(contact.receive_frequency_hz, 7_117_000)
        self.assertEqual(contact.transmit_frequency_hz, 7_107_000)
        manager.update_turn(TurnState.PEER_PASSED_TURN)
        self.assertEqual(manager.active.turn_state, TurnState.PEER_PASSED_TURN)

    def test_manual_return_needs_no_peer_signal(self) -> None:
        manager = ContactManager()
        offered = manager.offer(
            local_callsign="N4EAC",
            normal_frequency_hz=7_117_000,
            reply_frequency_hz=7_107_000,
            mode="USB-D",
        )
        self.assertIs(manager.return_to_normal(), offered)
        self.assertIsNone(manager.active)

    def test_first_responder_binds_broadcast_offer(self) -> None:
        manager = ContactManager()
        manager.offer(
            local_callsign="N4EAC",
            normal_frequency_hz=7_117_000,
            reply_frequency_hz=7_107_000,
            mode="USB-D",
        )
        manager.bind_peer("w1aw", "Joe")
        self.assertEqual(manager.active.peer_callsign, "W1AW")
        self.assertEqual(manager.active.peer_name, "Joe")

    def test_reply_offset_is_limited_to_ten_khz(self) -> None:
        validate_reply_frequency(7_117_000, 7_107_000)
        with self.assertRaisesRegex(ValueError, "10 kHz"):
            validate_reply_frequency(7_117_000, 7_106_999)


if __name__ == "__main__":
    unittest.main()
