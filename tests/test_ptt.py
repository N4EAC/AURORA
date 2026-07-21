"""Tests for Aurora fail-safe PTT control."""

import unittest
from unittest.mock import MagicMock, call

from radio.ptt import PttController, PttMethod


class PttTests(unittest.TestCase):
    def test_cat_context_always_releases_ptt(self) -> None:
        cat = MagicMock()
        controller = PttController(PttMethod.CAT, cat=cat)
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with controller.transmit():
                self.assertTrue(controller.active)
                raise RuntimeError("test failure")
        self.assertFalse(controller.active)
        self.assertEqual(cat.set_ptt.call_args_list, [call(True), call(False)])

    def test_rts_method_uses_control_line(self) -> None:
        transport = MagicMock()
        controller = PttController(PttMethod.RTS, transport=transport)
        controller.set_active(True)
        controller.close()
        self.assertEqual(transport.set_rts.call_args_list, [call(True), call(False)])

    def test_failed_activation_does_not_set_active_state(self) -> None:
        cat = MagicMock()
        cat.set_ptt.side_effect = RuntimeError("radio unavailable")
        controller = PttController(PttMethod.CAT, cat=cat)
        with self.assertRaises(RuntimeError):
            controller.set_active(True)
        self.assertFalse(controller.active)


if __name__ == "__main__":
    unittest.main()
