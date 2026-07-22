"""Tests for Aurora application navigation helpers."""

import unittest
from unittest.mock import Mock

from gui.application import _show_channel_results


class ApplicationNavigationTests(unittest.TestCase):
    """Verify workspace navigation without requiring a graphical display."""

    def test_channel_results_can_be_opened_before_a_test(self) -> None:
        notebook = Mock()
        channel_results = object()

        _show_channel_results(notebook, channel_results)

        notebook.select.assert_called_once_with(channel_results)
        notebook.focus_set.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
