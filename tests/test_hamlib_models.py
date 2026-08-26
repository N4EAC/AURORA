"""Tests for Hamlib radio model discovery."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from radio.hamlib_models import list_radio_models, parse_model_list


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

    def test_windows_model_discovery_has_no_console(self) -> None:
        result = MagicMock(stdout="1 Hamlib Dummy 20230602.0 Beta RIG_MODEL_DUMMY")
        with (
            patch("radio.hamlib_models.Path.is_file", return_value=True),
            patch("radio.subprocess_support.platform.system", return_value="Windows"),
            patch("radio.hamlib_models.subprocess.run", return_value=result) as run,
        ):
            list_radio_models(Path("rigctld.exe"))
        self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)


if __name__ == "__main__":
    unittest.main()
