"""Tests for Hamlib radio model discovery."""

import unittest

from radio.hamlib_models import parse_model_list


class HamlibModelTests(unittest.TestCase):
    def test_parses_operator_readable_model_names(self) -> None:
        output = """
Rig #  Mfg Model                 Version Status Macro
  1 Hamlib Dummy                20230602.0 Beta RIG_MODEL_DUMMY
3073 Icom IC-7300               20240201.0 Stable RIG_MODEL_IC7300
"""
        models = parse_model_list(output)
        self.assertEqual(models[0].display_name, "Hamlib Dummy")
        self.assertEqual(models[1].model_id, 3073)
        self.assertEqual(models[1].display_name, "Icom IC-7300")


if __name__ == "__main__":
    unittest.main()
