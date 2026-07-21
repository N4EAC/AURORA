"""Tests for Aurora audio device discovery."""

import unittest
from unittest.mock import patch

from audio.device import list_audio_devices


DEVICES = [
    {
        "name": "Receiver",
        "max_input_channels": 2,
        "max_output_channels": 0,
        "default_samplerate": 48_000.0,
    },
    {
        "name": "Transceiver",
        "max_input_channels": 1,
        "max_output_channels": 2,
        "default_samplerate": 48_000.0,
    },
]


class AudioDeviceTests(unittest.TestCase):
    @patch("audio.device.sd.query_devices", return_value=DEVICES)
    def test_output_device_filter(self, query_devices) -> None:
        devices = list_audio_devices("output")
        query_devices.assert_called_once_with()
        self.assertEqual([device.name for device in devices], ["Transceiver"])
        self.assertEqual(devices[0].index, 1)


if __name__ == "__main__":
    unittest.main()
