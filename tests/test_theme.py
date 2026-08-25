"""Tests for Aurora's cross-platform visual system."""

import unittest
from dataclasses import fields

from gui.theme import AuroraPalette, font_families


class ThemeTests(unittest.TestCase):
    """Verify platform-specific choices without initializing Tkinter."""

    def test_platform_font_families(self) -> None:
        self.assertEqual(font_families("Darwin"), ("SF Pro Text", "SF Mono"))
        self.assertEqual(font_families("Windows"), ("Segoe UI", "Cascadia Mono"))
        self.assertEqual(
            font_families("Linux"), ("DejaVu Sans", "DejaVu Sans Mono")
        )

    def test_palette_values_are_tk_colors(self) -> None:
        palette = AuroraPalette()
        for field in fields(palette):
            value = getattr(palette, field.name)
            self.assertRegex(value, r"^#[0-9a-fA-F]{6}$")


if __name__ == "__main__":
    unittest.main()
