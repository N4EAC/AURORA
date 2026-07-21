"""Serial radio-port discovery for Aurora."""

from dataclasses import dataclass

from serial.tools import list_ports


@dataclass(frozen=True, slots=True)
class SerialPort:
    """Serial port identity reported by the operating system."""

    device: str
    description: str
    hardware_id: str


def list_serial_ports() -> tuple[SerialPort, ...]:
    """Return serial ports currently visible to the host system."""
    return tuple(
        SerialPort(port.device, port.description, port.hwid)
        for port in sorted(list_ports.comports(), key=lambda item: item.device)
    )
