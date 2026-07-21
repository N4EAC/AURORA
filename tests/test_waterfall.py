"""Tests for Aurora waterfall history."""

import unittest

import numpy as np

from waterfall.model import WaterfallModel


class WaterfallTests(unittest.TestCase):
    def test_history_is_bounded_and_normalized(self) -> None:
        model = WaterfallModel(3, history_size=2, floor_db=-100.0, ceiling_db=0.0)
        model.add([-100.0, -50.0, 0.0])
        model.add([-75.0, -25.0, 10.0])
        model.add([-110.0, -50.0, -10.0])
        image = model.normalized_image()

        self.assertEqual(model.row_count, 2)
        self.assertEqual(image.shape, (2, 3))
        np.testing.assert_array_equal(image[1], [0, 128, 230])

    def test_wrong_bin_count_is_rejected(self) -> None:
        model = WaterfallModel(4)
        with self.assertRaisesRegex(ValueError, "bin count"):
            model.add([1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
