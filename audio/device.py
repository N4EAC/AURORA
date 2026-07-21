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


def list_audio_devices(kind: DeviceKind | None = None) -> tuple[AudioDevice, ...]:
    """Return available audio devices, optionally filtered by direction."""
    devices: list[AudioDevice] = []
    for index, details in enumerate(sd.query_devices()):
        device = AudioDevice(
            index=index,
            name=str(details["name"]),
            input_channels=int(details["max_input_channels"]),
            output_channels=int(details["max_output_channels"]),
            default_sample_rate=float(details["default_samplerate"]),
        )
        if kind == "input" and device.input_channels == 0:
            continue
        if kind == "output" and device.output_channels == 0:
            continue
        devices.append(device)
    return tuple(devices)
