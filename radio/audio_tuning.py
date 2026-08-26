"""Translate decoded audio offsets into safe radio dial-frequency changes."""

from __future__ import annotations


MODEM_AUDIO_CENTER_HZ = 1_500
MIN_AUDIO_HZ = 100
MAX_AUDIO_HZ = 3_000


def dial_frequency_for_audio_center(
    current_dial_hz: int,
    decoded_audio_hz: int,
    radio_mode: str,
    *,
    target_audio_hz: int = MODEM_AUDIO_CENTER_HZ,
) -> int:
    """Return the dial frequency that moves a decoded signal to *target_audio_hz*."""
    if current_dial_hz <= 0:
        raise ValueError("Current radio frequency must be positive")
    if not MIN_AUDIO_HZ <= decoded_audio_hz <= MAX_AUDIO_HZ:
        raise ValueError("Decoded audio center must be between 100 and 3000 Hz")
    if not MIN_AUDIO_HZ <= target_audio_hz <= MAX_AUDIO_HZ:
        raise ValueError("Target audio center must be between 100 and 3000 Hz")
    mode = radio_mode.strip().upper()
    if mode.startswith("USB") or mode.startswith("DIGU") or mode == "PKTUSB":
        adjustment = decoded_audio_hz - target_audio_hz
    elif mode.startswith("LSB") or mode.startswith("DIGL") or mode == "PKTLSB":
        adjustment = target_audio_hz - decoded_audio_hz
    else:
        raise ValueError("Station retuning requires a USB or LSB radio mode")
    tuned = current_dial_hz + adjustment
    if tuned <= 0:
        raise ValueError("Calculated radio frequency must be positive")
    return tuned
