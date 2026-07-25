"""Tests for Aurora audio device discovery."""

import unittest
from unittest.mock import patch

from audio.device import compatible_outputs, list_audio_devices, preferred_loopback_pair


HOST_APIS = [{"name": "MME"}, {"name": "WASAPI"}]


DEVICES = [
    {
        "name": "Receiver",
        "max_input_channels": 2,
        "max_output_channels": 0,
        "default_samplerate": 48_000.0,
        "hostapi": 0,
    },
    {
        "name": "Transceiver",
        "max_input_channels": 1,
        "max_output_channels": 2,
        "default_samplerate": 48_000.0,
        "hostapi": 0,
    },
    {
        "name": "CABLE Output",
        "max_input_channels": 2,
        "max_output_channels": 0,
        "default_samplerate": 48_000.0,
        "hostapi": 1,
    },
    {
        "name": "CABLE Input",
        "max_input_channels": 0,
        "max_output_channels": 2,
        "default_samplerate": 48_000.0,
        "hostapi": 1,
    },
]


class AudioDeviceTests(unittest.TestCase):
    @patch("audio.device.sd.query_hostapis", return_value=HOST_APIS)
    @patch("audio.device.sd.query_devices", return_value=DEVICES)
    def test_output_device_filter(self, query_devices, query_hostapis) -> None:
        devices = list_audio_devices("output")
        query_devices.assert_called_once_with()
        query_hostapis.assert_called_once_with()
        self.assertEqual(
            [device.name for device in devices],
            ["Transceiver", "CABLE Input"],
        )
        self.assertEqual(devices[0].index, 1)

    @patch("audio.device.sd.query_hostapis", return_value=HOST_APIS)
    @patch("audio.device.sd.query_devices", return_value=DEVICES)
    def test_pairing_prefers_compatible_virtual_cable(
        self, query_devices, query_hostapis
    ) -> None:
        inputs = list_audio_devices("input")
        outputs = list_audio_devices("output")
        pair = preferred_loopback_pair(inputs, outputs)
        self.assertIsNotNone(pair)
        self.assertEqual((pair[0].name, pair[1].name), ("CABLE Output", "CABLE Input"))
        self.assertEqual(
            [device.name for device in compatible_outputs(pair[0], outputs)],
            ["CABLE Input"],
        )


if __name__ == "__main__":
    unittest.main()
