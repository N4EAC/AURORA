"""Digit-selectable radio-frequency control for Aurora's Qt interface."""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QSpinBox


class DigitFrequencySpinBox(QSpinBox):
    """Tune the selected frequency digit with wheel or arrow-key input."""

    operatorFrequencyChanged = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setRange(100_000, 2_000_000_000)
        self.setValue(14_074_000)
        self.setAccelerated(False)
        self.setKeyboardTracking(False)
        self._digit_place = 0
        self._text_editing = False
        self.lineEdit().textEdited.connect(self._operator_text_edited)
        self.lineEdit().editingFinished.connect(self._operator_edit_finished)

    def operator_text_editing(self) -> bool:
        """Return whether typed text is awaiting operator confirmation."""
        return self._text_editing

    def set_synchronized_value(self, frequency_hz: int) -> None:
        """Set a linked frequency and immediately refresh its formatted text."""
        self.setValue(frequency_hz)
        self.lineEdit().setText(self.textFromValue(self.value()))
        self.lineEdit().setModified(False)
        self._text_editing = False
        self.update()

    def _operator_text_edited(self, text: str) -> None:
        """Protect an incomplete operator entry from asynchronous CAT status."""
        del text
        self._text_editing = True

    def textFromValue(self, value: int) -> str:  # noqa: N802
        return f"{value:,} Hz"

    def valueFromText(self, text: str) -> int:  # noqa: N802
        normalized = text.lower().replace(",", "").replace("khz", "")
        normalized = normalized.replace("hz", "").strip()
        try:
            entered = float(normalized)
        except ValueError:
            return self.minimum()
        frequency = entered * 1_000 if entered < self.minimum() else entered
        return int(round(frequency))

    def validate(self, text: str, position: int):  # noqa: ANN201
        """Accept either full Hz values or abbreviated integer-kHz values."""
        allowed = set("0123456789,. hzHZkK")
        if any(character not in allowed for character in text) or text.count(".") > 1:
            return QValidator.Invalid, text, position
        digits = "".join(character for character in text if character.isdigit())
        if not digits or text.rstrip().endswith("."):
            return QValidator.Intermediate, text, position
        frequency = self.valueFromText(text)
        if self.minimum() <= frequency <= self.maximum():
            return QValidator.Acceptable, text, position
        if frequency < self.minimum():
            return QValidator.Intermediate, text, position
        return QValidator.Invalid, text, position

    def _digit_indexes(self) -> list[int]:
        return [index for index, character in enumerate(self.lineEdit().text()) if character.isdigit()]

    def _select_digit(self, place: int) -> None:
        indexes = self._digit_indexes()
        if not indexes:
            return
        self._digit_place = max(0, min(place, len(indexes) - 1))
        self.lineEdit().setSelection(indexes[-1 - self._digit_place], 1)

    def _select_cursor_digit(self, cursor: int | None = None) -> None:
        indexes = self._digit_indexes()
        if not indexes:
            return
        position = self.lineEdit().cursorPosition() if cursor is None else cursor
        selected = min(
            range(len(indexes)), key=lambda index: abs(indexes[index] - position)
        )
        self._select_digit(len(indexes) - 1 - selected)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        local = self.lineEdit().mapFrom(self, event.position().toPoint())
        cursor = self.lineEdit().cursorPositionAt(local)
        super().mousePressEvent(event)
        if self.lineEdit().rect().contains(local):
            self._select_cursor_digit(cursor)

    def wheelEvent(self, event) -> None:  # noqa: N802
        direction = 1 if event.angleDelta().y() > 0 else -1
        self._change_selected_digit(direction)
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Left:
            self._select_digit(self._digit_place + 1)
            event.accept()
            return
        if event.key() == Qt.Key_Right:
            self._select_digit(self._digit_place - 1)
            event.accept()
            return
        if event.key() in (Qt.Key_Up, Qt.Key_Down):
            self._change_selected_digit(1 if event.key() == Qt.Key_Up else -1)
            event.accept()
            return
        super().keyPressEvent(event)

    def _change_selected_digit(self, direction: int) -> None:
        step = 10**self._digit_place
        self.setValue(self.value() + direction * step)
        self._select_digit(self._digit_place)
        self.operatorFrequencyChanged.emit(self.value())

    def _operator_edit_finished(self) -> None:
        self.interpretText()
        self._text_editing = False
        self.lineEdit().setModified(False)
        self._select_cursor_digit()
        self.operatorFrequencyChanged.emit(self.value())
