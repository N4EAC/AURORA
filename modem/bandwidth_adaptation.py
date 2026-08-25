"""Bounded automatic bandwidth selection for Aurora OFDM."""

from __future__ import annotations

from dataclasses import dataclass

from modem.mode_definition import AURORA_BANDWIDTH_MODES, ModeDefinition


@dataclass(frozen=True, slots=True)
class ChannelConditions:
    """Normalized measurements used by the bandwidth controller."""

    snr_db: float | None = None
    interference_ratio: float | None = None
    fading_depth: float | None = None
    multipath_delay_ms: float | None = None
    frequency_error_hz: float | None = None
    available_audio_passband_hz: float | None = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        for name in ("interference_ratio", "fading_depth", "confidence"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between zero and one")
        if self.multipath_delay_ms is not None and self.multipath_delay_ms < 0.0:
            raise ValueError("Multipath delay must not be negative")
        if (
            self.available_audio_passband_hz is not None
            and self.available_audio_passband_hz <= 0.0
        ):
            raise ValueError("Available audio passband must be positive")

    @property
    def complete(self) -> bool:
        """Return whether every required adaptation measurement is present."""
        return all(
            value is not None
            for value in (
                self.snr_db,
                self.interference_ratio,
                self.fading_depth,
                self.multipath_delay_ms,
                self.frequency_error_hz,
                self.available_audio_passband_hz,
            )
        )


@dataclass(frozen=True, slots=True)
class BandwidthDecision:
    """Selected mode plus an operator-visible adaptation explanation."""

    mode: ModeDefinition
    automatic: bool
    reason: str

    @property
    def bandwidth_hz(self) -> int:
        """Return the selected occupied-bandwidth ceiling."""
        return self.mode.occupied_bandwidth_hz


def select_bandwidth(conditions: ChannelConditions) -> BandwidthDecision:
    """Select the widest safe Aurora profile from trustworthy measurements."""
    if not conditions.complete or conditions.confidence < 0.70:
        return BandwidthDecision(
            AURORA_BANDWIDTH_MODES[500],
            True,
            "500 Hz fallback: channel estimate incomplete or low confidence",
        )

    assert conditions.snr_db is not None
    assert conditions.interference_ratio is not None
    assert conditions.fading_depth is not None
    assert conditions.multipath_delay_ms is not None
    assert conditions.frequency_error_hz is not None
    assert conditions.available_audio_passband_hz is not None
    frequency_error = abs(conditions.frequency_error_hz)

    if (
        conditions.available_audio_passband_hz >= 2_800.0
        and conditions.snr_db >= 12.0
        and conditions.interference_ratio <= 0.12
        and conditions.fading_depth <= 0.20
        and conditions.multipath_delay_ms <= 3.0
        and frequency_error <= 1.0
    ):
        return BandwidthDecision(
            AURORA_BANDWIDTH_MODES[2_800],
            True,
            "2.8 kHz: high-confidence clean and stable channel",
        )

    if (
        conditions.available_audio_passband_hz >= 2_300.0
        and conditions.snr_db >= 4.0
        and conditions.interference_ratio <= 0.35
        and conditions.fading_depth <= 0.45
        and conditions.multipath_delay_ms <= 8.0
        and frequency_error <= 3.0
    ):
        return BandwidthDecision(
            AURORA_BANDWIDTH_MODES[2_300],
            True,
            "2.3 kHz: usable channel with bounded impairment",
        )

    return BandwidthDecision(
        AURORA_BANDWIDTH_MODES[500],
        True,
        "500 Hz: weak, impaired, unstable, or passband-limited channel",
    )


def fixed_bandwidth(bandwidth_hz: int) -> BandwidthDecision:
    """Return an explicit operator-selected profile without automatic changes."""
    try:
        mode = AURORA_BANDWIDTH_MODES[bandwidth_hz]
    except KeyError as error:
        raise ValueError("Bandwidth must be 500, 2300, or 2800 Hz") from error
    return BandwidthDecision(mode, False, f"{bandwidth_hz} Hz operator selection")
