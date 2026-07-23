"""Deterministic payload feasibility study for Aurora's Deep objective."""

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
import math
import time

import numpy as np

from audio.buffer import AudioBuffer
from dsp.audio_channel import (
    AudioChannelConfig,
    apply_audio_channel,
    reference_noise_variance,
)
from dsp.deep_codec import (
    K10_RATE_QUARTER_GENERATORS,
    DeepCodecConfig,
    decode_deep_likelihoods,
    encode_deep_payload,
)
from dsp.deep_waveform import (
    DEEP_SYMBOL_RATE,
    modulate_deep_audio,
    recover_deep_likelihoods,
)
from dsp.framing import FrameError


EventCallback = Callable[[str, dict[str, object]], None]
REFERENCE_PAYLOAD = b"Aurora Deep message!"


@dataclass(frozen=True, slots=True)
class DeepChannelProfile:
    """Named offline channel conditions for payload research."""

    name: str
    channel: AudioChannelConfig = AudioChannelConfig(snr_db=None)


DEEP_CHANNEL_PROFILES = {
    profile.name: profile
    for profile in (
        DeepChannelProfile("AWGN reference"),
        DeepChannelProfile(
            "Moderate HF simulation",
            AudioChannelConfig(
                snr_db=None,
                timing_offset_samples=0.35,
                clock_error_ppm=20.0,
                multipath_delay_ms=2.0,
                multipath_gain=0.20,
                fading_depth=0.35,
                fading_cycles_per_frame=1.0,
                impulse_probability=0.00002,
                impulse_scale=2.0,
            ),
        ),
        DeepChannelProfile(
            "Severe HF simulation",
            AudioChannelConfig(
                snr_db=None,
                timing_offset_samples=0.75,
                clock_error_ppm=75.0,
                multipath_delay_ms=5.0,
                multipath_gain=0.45,
                fading_depth=0.65,
                fading_cycles_per_frame=2.0,
                impulse_probability=0.00005,
                impulse_scale=5.0,
            ),
        ),
        DeepChannelProfile(
            "Fading only",
            AudioChannelConfig(
                snr_db=None,
                fading_depth=0.65,
                fading_cycles_per_frame=2.0,
            ),
        ),
        DeepChannelProfile(
            "Multipath only",
            AudioChannelConfig(
                snr_db=None,
                multipath_delay_ms=5.0,
                multipath_gain=0.45,
            ),
        ),
        DeepChannelProfile(
            "Clock error only",
            AudioChannelConfig(snr_db=None, clock_error_ppm=75.0),
        ),
        DeepChannelProfile(
            "Impulsive noise only",
            AudioChannelConfig(
                snr_db=None,
                impulse_probability=0.00005,
                impulse_scale=5.0,
            ),
        ),
    )
}


@dataclass(frozen=True, slots=True)
class DeepCandidate:
    """One provisional coding and interleaving combination."""

    name: str
    codec: DeepCodecConfig


DEFAULT_DEEP_CANDIDATES = (
    DeepCandidate("rate-1/2, 16-column", DeepCodecConfig(1, 16)),
    DeepCandidate("repeated rate-1/4, 16-column", DeepCodecConfig(2, 16)),
    DeepCandidate("repeated rate-1/4, 32-column", DeepCodecConfig(2, 32)),
    DeepCandidate(
        "native rate-1/4, 16-column",
        DeepCodecConfig(1, 16, "native_rate_quarter"),
    ),
    DeepCandidate(
        "native rate-1/4, 32-column",
        DeepCodecConfig(1, 32, "native_rate_quarter"),
    ),
    DeepCandidate(
        "K10 native rate-1/4, 32-column",
        DeepCodecConfig(
            1,
            32,
            "native_rate_quarter",
            10,
            K10_RATE_QUARTER_GENERATORS,
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class DeepStudyConfig:
    """Inputs for a small, reproducible payload feasibility run."""

    snr_points_db: tuple[float, ...] = (-18.0, -20.0, -21.0, -22.0, -23.0, -24.0)
    seeds: tuple[int, ...] = (2026, 2027)
    noise_trials: int = 2
    payload: bytes = REFERENCE_PAYLOAD
    profile: DeepChannelProfile = DEEP_CHANNEL_PROFILES["AWGN reference"]
    candidates: tuple[DeepCandidate, ...] = DEFAULT_DEEP_CANDIDATES
    reference_bandwidth_hz: float = 2_500.0
    leading_silence_samples: int = 731
    frequency_offset_hz: float = 2.0
    frequency_search_hz: tuple[float, ...] = (-2.0, -1.0, 0.0, 1.0, 2.0)
    clock_search_ppm: tuple[float, ...] = (
        -100.0,
        -75.0,
        -20.0,
        0.0,
        20.0,
        75.0,
        100.0,
    )
    acquisition_score_threshold: float = 3.0
    minimum_pilot_quality: float = 0.15
    tracking_options: tuple[bool, ...] = (False, True)

    def __post_init__(self) -> None:
        if len(self.payload) != 20:
            raise ValueError("Deep reference payload must contain exactly 20 bytes")
        if not self.snr_points_db or not self.seeds or not self.candidates:
            raise ValueError("Deep study selections must not be empty")
        if self.noise_trials < 0:
            raise ValueError("Noise trial count must not be negative")
        if self.reference_bandwidth_hz <= 0.0:
            raise ValueError("Reference bandwidth must be positive")
        if not self.clock_search_ppm:
            raise ValueError("Clock search grid must not be empty")
        if not self.frequency_search_hz:
            raise ValueError("Frequency search grid must not be empty")
        if not self.tracking_options:
            raise ValueError("Tracking comparison must not be empty")
        if self.minimum_pilot_quality < 0.0:
            raise ValueError("Minimum pilot quality must not be negative")


@dataclass(frozen=True, slots=True)
class DeepStudyPoint:
    """CRC-confirmed outcomes for one candidate and SNR point."""

    candidate: str
    tracking_enabled: bool
    snr_db: float
    trials: int
    acquired: int
    decoded: int
    crc_failures: int
    acquisition_failures: int
    carrier_tracking_failures: int
    false_decodes: int
    noise_trials: int
    duration_seconds: float
    information_rate_bps: float
    elapsed_seconds: float
    mean_acquisition_score: float
    mean_pilot_quality: float

    @property
    def delivery_rate_percent(self) -> float:
        """Return CRC-confirmed payload delivery percentage."""
        return 0.0 if self.trials == 0 else 100.0 * self.decoded / self.trials


@dataclass(frozen=True, slots=True)
class DeepStudyResult:
    """Ordered feasibility results with explicit non-protocol status."""

    points: tuple[DeepStudyPoint, ...]
    cancelled: bool
    elapsed_seconds: float
    measurement_domain: str = "deep_payload_research"
    over_the_air_protocol: bool = False


@dataclass(frozen=True, slots=True)
class DeepDecodeOutcome:
    """Receiver-stage result retained even when CRC validation fails."""

    payload_matches: bool
    crc_failed: bool
    acquisition_score: float
    pilot_quality: float


def _emit(
    callback: EventCallback | None,
    event: str,
    **fields: object,
) -> None:
    if callback is not None:
        callback(event, fields)


def _noise_only_audio(
    reference: AudioBuffer,
    snr_db: float,
    bandwidth_hz: float,
    random: np.random.Generator,
) -> AudioBuffer:
    signal_power = float(np.mean(np.asarray(reference.samples, dtype=np.float64) ** 2))
    variance = reference_noise_variance(
        signal_power,
        snr_db,
        reference.sample_rate,
        bandwidth_hz,
    )
    samples = random.normal(0.0, math.sqrt(variance), reference.frame_count)
    return AudioBuffer(samples.astype(np.float32), reference.sample_rate)


def _decode_audio(
    audio: AudioBuffer,
    coded_bit_count: int,
    candidate: DeepCandidate,
    config: DeepStudyConfig,
    tracking_enabled: bool,
) -> DeepDecodeOutcome:
    recovered = recover_deep_likelihoods(
        audio,
        coded_bit_count,
        clock_search_ppm=config.clock_search_ppm,
        frequency_search_hz=config.frequency_search_hz,
        acquisition_score_threshold=config.acquisition_score_threshold,
        tracking_enabled=tracking_enabled,
    )
    if (
        tracking_enabled
        and recovered.pilot_quality < config.minimum_pilot_quality
    ):
        raise CarrierTrackingError("Deep pilot quality is below threshold")
    try:
        frame = decode_deep_likelihoods(recovered.likelihoods, candidate.codec)
    except FrameError:
        return DeepDecodeOutcome(
            False,
            True,
            recovered.acquisition_score,
            recovered.pilot_quality,
        )
    return DeepDecodeOutcome(
        frame.payload == config.payload,
        False,
        recovered.acquisition_score,
        recovered.pilot_quality,
    )


class CarrierTrackingError(ValueError):
    """Raised when acquisition succeeds but distributed pilots are unusable."""


def run_deep_mode_study(
    config: DeepStudyConfig = DeepStudyConfig(),
    *,
    should_continue: Callable[[], bool] = lambda: True,
    event_callback: EventCallback | None = None,
) -> DeepStudyResult:
    """Run offline signal and noise trials without opening audio or radio hardware."""
    started = time.perf_counter()
    points: list[DeepStudyPoint] = []
    cancelled = False
    _emit(
        event_callback,
        "DEEP_STUDY_START",
        payload_bytes=len(config.payload),
        profile=config.profile.name,
        snr_points_db=config.snr_points_db,
        over_the_air_protocol=False,
    )

    for candidate in config.candidates:
        encoded = encode_deep_payload(config.payload, candidate.codec)
        clean = modulate_deep_audio(
            encoded.bits,
            leading_silence_samples=config.leading_silence_samples,
            frequency_offset_hz=config.frequency_offset_hz,
        )
        information_rate = 8.0 * len(config.payload) / clean.duration_seconds
        for tracking_enabled in config.tracking_options:
            for snr_db in config.snr_points_db:
                point_started = time.perf_counter()
                acquired = decoded = crc_failures = acquisition_failures = 0
                carrier_tracking_failures = 0
                acquisition_scores: list[float] = []
                pilot_qualities: list[float] = []
                completed = 0
                false_decodes = completed_noise = 0
                channel = replace(
                    config.profile.channel,
                    snr_db=snr_db,
                    reference_bandwidth_hz=config.reference_bandwidth_hz,
                )
                for seed in config.seeds:
                    if not should_continue():
                        cancelled = True
                        break
                    impaired = apply_audio_channel(
                        clean,
                        channel,
                        np.random.default_rng(seed),
                    )
                    completed += 1
                    try:
                        outcome = _decode_audio(
                            impaired,
                            len(encoded.bits),
                            candidate,
                            config,
                            tracking_enabled,
                        )
                        acquired += 1
                        acquisition_scores.append(outcome.acquisition_score)
                        pilot_qualities.append(outcome.pilot_quality)
                        decoded += int(outcome.payload_matches)
                        crc_failures += int(outcome.crc_failed)
                    except CarrierTrackingError:
                        acquired += 1
                        carrier_tracking_failures += 1
                    except ValueError:
                        acquisition_failures += 1

                if not cancelled:
                    for noise_index in range(config.noise_trials):
                        if not should_continue():
                            cancelled = True
                            break
                        noise = _noise_only_audio(
                            clean,
                            snr_db,
                            config.reference_bandwidth_hz,
                            np.random.default_rng(1_000_000 + noise_index),
                        )
                        completed_noise += 1
                        try:
                            outcome = _decode_audio(
                                noise,
                                len(encoded.bits),
                                candidate,
                                config,
                                tracking_enabled,
                            )
                            false_decodes += int(outcome.payload_matches)
                        except (FrameError, ValueError):
                            pass

                point = DeepStudyPoint(
                    candidate.name,
                    tracking_enabled,
                    snr_db,
                    completed,
                    acquired,
                    decoded,
                    crc_failures,
                    acquisition_failures,
                    carrier_tracking_failures,
                    false_decodes,
                    completed_noise,
                    clean.duration_seconds,
                    information_rate,
                    time.perf_counter() - point_started,
                    (
                        float(np.mean(acquisition_scores))
                        if acquisition_scores
                        else 0.0
                    ),
                    (
                        float(np.mean(pilot_qualities))
                        if pilot_qualities
                        else 0.0
                    ),
                )
                points.append(point)
                _emit(event_callback, "DEEP_STUDY_POINT", **asdict(point))
                if cancelled:
                    break
            if cancelled:
                break
        if cancelled:
            break

    elapsed = time.perf_counter() - started
    _emit(
        event_callback,
        "DEEP_STUDY_END",
        points=len(points),
        cancelled=cancelled,
        elapsed_seconds=elapsed,
        over_the_air_protocol=False,
    )
    return DeepStudyResult(tuple(points), cancelled, elapsed)
