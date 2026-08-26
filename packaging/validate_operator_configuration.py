"""Validate operator-facing modem constants before native packaging."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from radio.audio_tuning import MAX_AUDIO_HZ, MIN_AUDIO_HZ, MODEM_AUDIO_CENTER_HZ
from modem.chat_transport import CHAT_VERSION
from modem.contact_session import (
    DEFAULT_REPLY_WINDOW_SECONDS,
    MAX_REPLY_OFFSET_HZ,
)
from radio.split_control import FakeSplitController


def validate() -> None:
    """Reject a build whose RF/audio tuning contract is inconsistent."""
    if MODEM_AUDIO_CENTER_HZ != 1_500:
        raise RuntimeError("Native builds require Aurora's 1500 Hz modem center")
    if (MIN_AUDIO_HZ, MAX_AUDIO_HZ) != (100, 3_000):
        raise RuntimeError("Native builds require the 100–3000 Hz receive passband")
    if CHAT_VERSION < 3:
        raise RuntimeError("Native builds require Reply Channel chat metadata")
    if MAX_REPLY_OFFSET_HZ != 10_000:
        raise RuntimeError("Native builds require the ±10 kHz Reply Channel limit")
    if DEFAULT_REPLY_WINDOW_SECONDS != 120:
        raise RuntimeError("Native builds require the 120-second reply window default")
    if not callable(getattr(FakeSplitController, "restore", None)):
        raise RuntimeError("Native builds require manual fake-split restoration")
    print(
        "Verified operator tuning: Hamlib RF dial, "
        f"fixed {MODEM_AUDIO_CENTER_HZ} Hz modem center, "
        f"{MIN_AUDIO_HZ}–{MAX_AUDIO_HZ} Hz receive scan, "
        f"Reply Channel ±{MAX_REPLY_OFFSET_HZ // 1_000} kHz with local return"
    )


if __name__ == "__main__":
    validate()
