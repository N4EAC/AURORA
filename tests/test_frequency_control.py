"""Tests for Aurora's digit-selectable Qt frequency control."""

import os
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from gui.frequency_control import DigitFrequencySpinBox


class FrequencyControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_arrow_keys_tune_selected_digit(self) -> None:
        control = DigitFrequencySpinBox()
        control.setValue(14_074_000)
        control._select_digit(2)
        QTest.keyClick(control, Qt.Key_Up)
        self.assertEqual(control.value(), 14_074_100)
        QTest.keyClick(control, Qt.Key_Right)
        QTest.keyClick(control, Qt.Key_Down)
        self.assertEqual(control.value(), 14_074_090)

    def test_mouse_wheel_tunes_selected_digit(self) -> None:
        control = DigitFrequencySpinBox()
        control.setValue(14_074_000)
        control._select_digit(3)
        event = MagicMock()
        event.angleDelta.return_value.y.return_value = 120
        control.wheelEvent(event)
        self.assertEqual(control.value(), 14_075_000)
        event.accept.assert_called_once_with()

    def test_frequency_text_is_grouped_and_parseable(self) -> None:
        control = DigitFrequencySpinBox()
        self.assertEqual(control.textFromValue(14_074_000), "14,074,000 Hz")
        self.assertEqual(control.valueFromText("14,074,010 Hz"), 14_074_010)
        self.assertEqual(control.valueFromText("7117"), 7_117_000)
        self.assertEqual(control.valueFromText("14074 kHz"), 14_074_000)
        self.assertEqual(control.valueFromText("7117.5 kHz"), 7_117_500)

    def test_typed_frequency_waits_for_enter(self) -> None:
        control = DigitFrequencySpinBox()
        control.show()
        control.lineEdit().setText("7117000")
        control.lineEdit().textEdited.emit("7117000")
        self.assertTrue(control.operator_text_editing())
        self.assertEqual(control.value(), 14_074_000)
        control._operator_edit_finished()
        self.assertFalse(control.operator_text_editing())
        self.assertEqual(control.value(), 7_117_000)

    def test_short_typed_frequency_is_interpreted_as_khz(self) -> None:
        control = DigitFrequencySpinBox()
        control.lineEdit().setText("7117")
        control.lineEdit().textEdited.emit("7117")
        control._operator_edit_finished()
        self.assertEqual(control.value(), 7_117_000)
        self.assertEqual(control.lineEdit().text(), "7,117,000 Hz")

    def test_synchronized_value_refreshes_visible_text(self) -> None:
        control = DigitFrequencySpinBox()
        control.lineEdit().setText("stale")
        control.lineEdit().textEdited.emit("stale")
        control.set_synchronized_value(7_117_000)
        self.assertEqual(control.value(), 7_117_000)
        self.assertEqual(control.lineEdit().text(), "7,117,000 Hz")
        self.assertFalse(control.operator_text_editing())

    def test_decimal_khz_entry_and_selected_khz_digit(self) -> None:
        control = DigitFrequencySpinBox()
        control.lineEdit().setText("7117.5")
        control.lineEdit().textEdited.emit("7117.5")
        control._operator_edit_finished()
        self.assertEqual(control.value(), 7_117_500)
        control._select_cursor_digit(4)
        self.assertEqual(control._digit_place, 3)
        control._change_selected_digit(1)
        self.assertEqual(control.value(), 7_118_500)


if __name__ == "__main__":
    unittest.main()
