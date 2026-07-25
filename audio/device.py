"""Audio device discovery for Aurora."""

from dataclasses import dataclass
from typing import Literal

import sounddevice as sd


DeviceKind = Literal["input", "output"]


@dataclass(frozen=True, slots=True)
class AudioDevice:
    """Audio device capabilities reported by the host system."""

    index: int
    name: str
    input_channels: int
    output_channels: int
    default_sample_rate: float
    host_api_index: int
    host_api_name: str


def list_audio_devices(kind: DeviceKind | None = None) -> tuple[AudioDevice, ...]:
    """Return available audio devices, optionally filtered by direction."""
    devices: list[AudioDevice] = []
    host_apis = sd.query_hostapis()
    for index, details in enumerate(sd.query_devices()):
        host_api_index = int(details["hostapi"])
        device = AudioDevice(
            index=index,
            name=str(details["name"]),
            input_channels=int(details["max_input_channels"]),
            output_channels=int(details["max_output_channels"]),
            default_sample_rate=float(details["default_samplerate"]),
            host_api_index=host_api_index,
            host_api_name=str(host_apis[host_api_index]["name"]),
        )
        if kind == "input" and device.input_channels == 0:
            continue
        if kind == "output" and device.output_channels == 0:
            continue
        devices.append(device)
    return tuple(devices)


def compatible_outputs(
    input_device: AudioDevice,
    output_devices: tuple[AudioDevice, ...],
) -> tuple[AudioDevice, ...]:
    """Return outputs that PortAudio can combine with the selected input."""
    return tuple(
        device
        for device in output_devices
        if device.host_api_index == input_device.host_api_index
    )


def preferred_loopback_pair(
    input_devices: tuple[AudioDevice, ...],
    output_devices: tuple[AudioDevice, ...],
) -> tuple[AudioDevice, AudioDevice] | None:
    """Prefer a compatible virtual-cable input/output pair when discoverable."""
    for input_device in input_devices:
        compatible = compatible_outputs(input_device, output_devices)
        for output_device in compatible:
            names = f"{input_device.name} {output_device.name}".lower()
            if "cable output" in names and "cable input" in names:
                return input_device, output_device
    for input_device in input_devices:
        compatible = compatible_outputs(input_device, output_devices)
        if compatible:
            return input_device, compatible[0]
    return None
