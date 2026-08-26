"""Digit-selectable radio-frequency control for Aurora's Qt interface."""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QSpinBox


class DigitFrequencySpinBox(QSpinBox):
    """Tune the selected frequency digit with wheel or arrow-key input."""

    operatorFrequencyChanged = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setRange(100_000, 2_000_000_000)
        self.setValue(14_074_000)
        self.setAccelerated(False)
        self._digit_place = 0
        self.lineEdit().editingFinished.connect(self._operator_edit_finished)

    def textFromValue(self, value: int) -> str:  # noqa: N802
        return f"{value:,} Hz"

    def valueFromText(self, text: str) -> int:  # noqa: N802
        digits = "".join(character for character in text if character.isdigit())
        return int(digits or self.minimum())

    def _digit_indexes(self) -> list[int]:
        return [index for index, character in enumerate(self.lineEdit().text()) if character.isdigit()]

    def _select_digit(self, place: int) -> None:
        indexes = self._digit_indexes()
        if not indexes:
            return
        self._digit_place = max(0, min(place, len(indexes) - 1))
        self.lineEdit().setSelection(indexes[-1 - self._digit_place], 1)

    def _select_cursor_digit(self) -> None:
        indexes = self._digit_indexes()
        if not indexes:
            return
        cursor = self.lineEdit().cursorPosition()
        selected = min(range(len(indexes)), key=lambda index: abs(indexes[index] - cursor))
        self._select_digit(len(indexes) - 1 - selected)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        super().mousePressEvent(event)
        self._select_cursor_digit()

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
        self._select_cursor_digit()
        self.operatorFrequencyChanged.emit(self.value())
