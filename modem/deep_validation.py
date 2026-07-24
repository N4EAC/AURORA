"""Batched validation campaigns for the provisional Aurora Deep candidate."""

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from itertools import product
import math
import time
import tracemalloc

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
    DeepWaveformResult,
    modulate_deep_audio,
    recover_deep_candidate_likelihoods,
)
from dsp.framing import FrameError
from modem.deep_mode_study import (
    DEEP_CHANNEL_PROFILES,
    DeepChannelProfile,
    REFERENCE_PAYLOAD,
)
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition


EventCallback = Callable[[str, dict[str, object]], None]
K10_DEEP_CODEC = DeepCodecConfig(
    1,
    32,
    "native_rate_quarter",
    10,
    K10_RATE_QUARTER_GENERATORS,
)


@dataclass(frozen=True, slots=True)
class DeepValidationConfig:
    """Select a deterministic, optionally batched validation campaign."""

    signal_trials: int = 1_000
    noise_trials: int = 10_000
    start_trial: int = 0
    batch_size: int | None = None
    snr_db: float = -24.0
    reference_bandwidth_hz: float = 2_500.0
    payload: bytes = REFERENCE_PAYLOAD
    codec: DeepCodecConfig = K10_DEEP_CODEC
    profile: DeepChannelProfile = DEEP_CHANNEL_PROFILES["AWGN reference"]
    seed_base: int = 50_000
    leading_silence_samples: int = 731
    frequency_offsets_hz: tuple[float, ...] = (0.0,)
    frequency_search_hz: tuple[float, ...] = (0.0,)
    clock_offsets_ppm: tuple[float, ...] = (0.0,)
    clock_search_ppm: tuple[float, ...] = (0.0,)
    measure_memory: bool = False
    acquisition_score_threshold: float = 5.0
    fading_equalization: bool = False
    erasure_gain_ratio: float = 0.0
    fading_activation_gain_ratio: float = 0.6
    fading_confidence_threshold: float = 0.5
    acquisition_diversity: bool = False
    acquisition_diversity_score_threshold: float = 0.37
    acquisition_diversity_coherent_threshold: float = 1.0
    pilot_interval: int = 128
    pilot_symbol_count: int = 16
    mode: ModeDefinition = AURORA_ROBUST_MODE
    soft_observation_count: int = 1

    def __post_init__(self) -> None:
        if min(self.signal_trials, self.noise_trials, self.start_trial) < 0:
            raise ValueError("Validation trial counts must not be negative")
        if self.batch_size is not None and self.batch_size <= 0:
            raise ValueError("Batch size must be positive")
        if len(self.payload) != 20:
            raise ValueError("Validation payload must contain exactly 20 bytes")
        if not all(
            (
                self.frequency_offsets_hz,
                self.frequency_search_hz,
                self.clock_offsets_ppm,
                self.clock_search_ppm,
            )
        ):
            raise ValueError("Offset and search grids must not be empty")
        if self.acquisition_score_threshold <= 0.0:
            raise ValueError("Acquisition score threshold must be positive")
        if not 0.0 <= self.erasure_gain_ratio < 1.0:
            raise ValueError("Erasure gain ratio must be between zero and one")
        if not 0.0 <= self.fading_activation_gain_ratio <= 1.0:
            raise ValueError(
                "Fading activation gain ratio must be between zero and one"
            )
        if self.fading_confidence_threshold <= 0.0:
            raise ValueError("Fading confidence threshold must be positive")
        if not 0.0 <= self.acquisition_diversity_score_threshold <= 1.0:
            raise ValueError(
                "Acquisition diversity score threshold must be between zero and one"
            )
        if self.acquisition_diversity_coherent_threshold <= 0.0:
            raise ValueError(
                "Acquisition diversity coherent threshold must be positive"
            )
        if self.pilot_interval <= 0 or self.pilot_symbol_count <= 0:
            raise ValueError("Pilot geometry values must be positive")
        if self.soft_observation_count <= 0:
            raise ValueError("Soft observation count must be positive")


@dataclass(frozen=True, slots=True)
class DeepValidationResult:
    """CRC-confirmed outcomes and resource measurements for one batch."""

    signal_trials: int
    decoded: int
    acquisition_failures: int
    crc_failures: int
    noise_trials: int
    false_decodes: int
    start_trial: int
    next_trial: int
    cancelled: bool
    elapsed_seconds: float
    mean_signal_seconds: float
    peak_memory_bytes: int
    delivery_confidence_95: tuple[float, float]
    false_decode_confidence_95: tuple[float, float]
    mean_minimum_relative_gain: float
    mean_erased_symbol_percent: float
    fading_equalized_trials: int
    mean_channel_variation_confidence: float
    mean_acquisition_diversity_score: float
    measurement_domain: str = "deep_k10_validation"
    over_the_air_protocol: bool = False


def _wilson(successes: int, trials: int) -> tuple[float, float]:
    if trials == 0:
        return 0.0, 0.0
    z = 1.959963984540054
    rate = successes / trials
    denominator = 1.0 + z * z / trials
    center = (rate + z * z / (2.0 * trials)) / denominator
    radius = z * math.sqrt(
        rate * (1.0 - rate) / trials + z * z / (4.0 * trials * trials)
    ) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def _noise_audio(
    reference: AudioBuffer,
    config: DeepValidationConfig,
    random: np.random.Generator,
) -> AudioBuffer:
    power = float(np.mean(np.asarray(reference.samples, dtype=np.float64) ** 2))
    variance = reference_noise_variance(
        power,
        config.snr_db,
        reference.sample_rate,
        config.reference_bandwidth_hz,
    )
    samples = random.normal(0.0, math.sqrt(variance), reference.frame_count)
    return AudioBuffer(samples.astype(np.float32), reference.sample_rate)


def _decode_candidates(
    audio: AudioBuffer,
    coded_bit_count: int,
    config: DeepValidationConfig,
) -> tuple[bool, bool, bool, float, float, bool, float, float]:
    common_options = {
        "clock_search_ppm": config.clock_search_ppm,
        "frequency_search_hz": config.frequency_search_hz,
        "erasure_gain_ratio": config.erasure_gain_ratio,
        "fading_activation_gain_ratio": config.fading_activation_gain_ratio,
        "fading_confidence_threshold": config.fading_confidence_threshold,
        "pilot_interval": config.pilot_interval,
        "pilot_symbol_count": config.pilot_symbol_count,
        "mode": config.mode,
    }
    primary_candidates = recover_deep_candidate_likelihoods(
        audio,
        coded_bit_count,
        fading_equalization=False,
        acquisition_diversity=False,
        **common_options,
    )
    if not primary_candidates:
        return False, False, False, 0.0, 0.0, False, 0.0, 0.0
    primary_acquired = (
        primary_candidates[0].acquisition_score
        >= config.acquisition_score_threshold
    )
    diversity_candidates: tuple[DeepWaveformResult, ...] = ()
    diversity_acquired = False
    if config.acquisition_diversity and not primary_acquired:
        diversity_candidates = recover_deep_candidate_likelihoods(
            audio,
            coded_bit_count,
            fading_equalization=False,
            acquisition_diversity=True,
            **common_options,
        )
        diversity_acquired = bool(diversity_candidates) and (
            diversity_candidates[0].acquisition_score
            >= config.acquisition_diversity_coherent_threshold
        ) and (
            diversity_candidates[0].acquisition_diversity_score
            >= config.acquisition_diversity_score_threshold
        )
    diversity_score = (
        diversity_candidates[0].acquisition_diversity_score
        if diversity_candidates
        else primary_candidates[0].acquisition_diversity_score
    )
    if not primary_acquired and not diversity_acquired:
        return False, False, False, 0.0, 0.0, False, 0.0, diversity_score

    baseline_candidates = (
        primary_candidates if primary_acquired else diversity_candidates
    )
    for candidate in baseline_candidates:
        try:
            frame = decode_deep_likelihoods(
                candidate.likelihoods,
                config.codec,
            )
        except (FrameError, ValueError):
            continue
        return (
            True,
            True,
            frame.payload == config.payload,
            candidate.minimum_relative_gain,
            candidate.erased_symbol_percent,
            False,
            0.0,
            diversity_score,
        )
    experimental_candidates: tuple[DeepWaveformResult, ...] = ()
    if config.fading_equalization:
        experimental_candidates = recover_deep_candidate_likelihoods(
            audio,
            coded_bit_count,
            fading_equalization=True,
            acquisition_diversity=diversity_acquired,
            **common_options,
        )
        experimental_candidates = tuple(
            candidate
            for candidate in experimental_candidates
            if candidate.fading_equalization_enabled
        )
    variation_confidence = max(
        (
            candidate.channel_variation_confidence
            for candidate in experimental_candidates
        ),
        default=0.0,
    )
    for candidate in experimental_candidates:
        try:
            frame = decode_deep_likelihoods(
                candidate.likelihoods,
                config.codec,
            )
        except (FrameError, ValueError):
            continue
        return (
            True,
            True,
            frame.payload == config.payload,
            candidate.minimum_relative_gain,
            candidate.erased_symbol_percent,
            True,
            variation_confidence,
            diversity_score,
        )
    return (
        True,
        False,
        False,
        baseline_candidates[0].minimum_relative_gain,
        baseline_candidates[0].erased_symbol_percent,
        False,
        variation_confidence,
        diversity_score,
    )


def _decode_soft_observations(
    audio_observations: tuple[AudioBuffer, ...],
    coded_bit_count: int,
    config: DeepValidationConfig,
) -> tuple[bool, bool, bool, float, float, bool, float, float]:
    """Combine independently received, acquired observations before FEC."""
    if len(audio_observations) == 1:
        return _decode_candidates(audio_observations[0], coded_bit_count, config)

    observation_candidates: list[tuple[DeepWaveformResult, ...]] = []
    for audio in audio_observations:
        common_options = {
            "clock_search_ppm": config.clock_search_ppm,
            "frequency_search_hz": config.frequency_search_hz,
            "erasure_gain_ratio": config.erasure_gain_ratio,
            "fading_equalization": False,
            "fading_activation_gain_ratio": config.fading_activation_gain_ratio,
            "fading_confidence_threshold": config.fading_confidence_threshold,
            "pilot_interval": config.pilot_interval,
            "pilot_symbol_count": config.pilot_symbol_count,
            "mode": config.mode,
        }
        recovered = recover_deep_candidate_likelihoods(
            audio,
            coded_bit_count,
            acquisition_diversity=False,
            **common_options,
        )
        accepted = tuple(
            candidate
            for candidate in recovered
            if candidate.acquisition_score >= config.acquisition_score_threshold
        )
        if not accepted and config.acquisition_diversity:
            recovered = recover_deep_candidate_likelihoods(
                audio,
                coded_bit_count,
                acquisition_diversity=True,
                **common_options,
            )
            accepted = tuple(
                candidate
                for candidate in recovered
                if (
                    candidate.acquisition_score
                    >= config.acquisition_diversity_coherent_threshold
                    and candidate.acquisition_diversity_score
                    >= config.acquisition_diversity_score_threshold
                )
            )
        if accepted:
            observation_candidates.append(accepted)
    if not observation_candidates:
        return False, False, False, 0.0, 0.0, False, 0.0, 0.0

    selected: tuple[DeepWaveformResult, ...] = tuple(
        candidates[0] for candidates in observation_candidates
    )
    valid = False
    for hypothesis in product(*observation_candidates):
        normalized: list[np.ndarray] = []
        for candidate in hypothesis:
            likelihoods = np.asarray(candidate.likelihoods, dtype=np.float64)
            scale = max(
                float(np.sqrt(np.mean(likelihoods * likelihoods))),
                np.finfo(float).tiny,
            )
            reliability = max(candidate.acquisition_diversity_score, 0.1)
            normalized.append(likelihoods * reliability / scale)
        combined = np.sum(np.asarray(normalized), axis=0)
        try:
            frame = decode_deep_likelihoods(combined, config.codec)
        except (FrameError, ValueError):
            continue
        valid = frame.payload == config.payload
        if valid:
            selected = hypothesis
            break
    return (
        True,
        valid,
        valid,
        min(candidate.minimum_relative_gain for candidate in selected),
        float(np.mean([candidate.erased_symbol_percent for candidate in selected])),
        any(candidate.fading_equalization_enabled for candidate in selected),
        float(np.mean([candidate.channel_variation_confidence for candidate in selected])),
        float(np.mean([candidate.acquisition_diversity_score for candidate in selected])),
    )


def run_deep_validation(
    config: DeepValidationConfig = DeepValidationConfig(),
    *,
    should_continue: Callable[[], bool] = lambda: True,
    event_callback: EventCallback | None = None,
) -> DeepValidationResult:
    """Run one deterministic batch without opening audio or radio hardware."""
    encoded = encode_deep_payload(config.payload, config.codec)
    clean_by_frequency = {
        offset: modulate_deep_audio(
            encoded.bits,
            leading_silence_samples=config.leading_silence_samples,
            frequency_offset_hz=offset,
            pilot_interval=config.pilot_interval,
            pilot_symbol_count=config.pilot_symbol_count,
            mode=config.mode,
        )
        for offset in config.frequency_offsets_hz
    }
    reference = clean_by_frequency[config.frequency_offsets_hz[0]]
    requested = config.signal_trials
    if config.batch_size is not None:
        requested = min(requested, config.batch_size)
    stop_trial = min(config.signal_trials, config.start_trial + requested)
    started = time.perf_counter()
    if config.measure_memory:
        tracemalloc.start()
    decoded = acquisition_failures = crc_failures = completed = 0
    minimum_gains: list[float] = []
    erased_percents: list[float] = []
    fading_equalized_trials = 0
    variation_confidences: list[float] = []
    diversity_scores: list[float] = []
    cancelled = False

    for trial in range(config.start_trial, stop_trial):
        if not should_continue():
            cancelled = True
            break
        frequency = config.frequency_offsets_hz[
            trial % len(config.frequency_offsets_hz)
        ]
        clock = config.clock_offsets_ppm[
            trial % len(config.clock_offsets_ppm)
        ]
        channel = replace(
            config.profile.channel,
            snr_db=config.snr_db,
            reference_bandwidth_hz=config.reference_bandwidth_hz,
            clock_error_ppm=config.profile.channel.clock_error_ppm + clock,
        )
        impaired = tuple(
            apply_audio_channel(
                clean_by_frequency[frequency],
                channel,
                np.random.default_rng(
                    config.seed_base
                    + trial
                    + observation * max(config.signal_trials, 1)
                ),
            )
            for observation in range(config.soft_observation_count)
        )
        (
            acquired,
            crc_valid,
            payload_match,
            minimum_gain,
            erased_percent,
            fading_equalized,
            variation_confidence,
            diversity_score,
        ) = _decode_soft_observations(impaired, len(encoded.bits), config)
        valid = crc_valid and payload_match
        completed += 1
        decoded += int(valid)
        acquisition_failures += int(not acquired)
        crc_failures += int(acquired and not valid)
        fading_equalized_trials += int(acquired and fading_equalized)
        if acquired:
            minimum_gains.append(minimum_gain)
            erased_percents.append(erased_percent)
            variation_confidences.append(variation_confidence)
            diversity_scores.append(diversity_score)
        if event_callback is not None:
            event_callback(
                "DEEP_VALIDATION_SIGNAL",
                {
                    "trial": trial,
                    "decoded": valid,
                    "frequency_offset_hz": frequency,
                    "clock_error_ppm": clock,
                },
            )

    completed_noise = false_decodes = 0
    if not cancelled and stop_trial == config.signal_trials:
        for noise_trial in range(config.noise_trials):
            if not should_continue():
                cancelled = True
                break
            noise = _noise_audio(
                reference,
                config,
                np.random.default_rng(config.seed_base + 10_000_000 + noise_trial),
            )
            _, crc_valid, _, _, _, _, _, _ = _decode_candidates(
                noise, len(encoded.bits), config
            )
            completed_noise += 1
            false_decodes += int(crc_valid)

    peak_memory = 0
    if config.measure_memory:
        _, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    elapsed = time.perf_counter() - started
    result = DeepValidationResult(
        completed,
        decoded,
        acquisition_failures,
        crc_failures,
        completed_noise,
        false_decodes,
        config.start_trial,
        config.start_trial + completed,
        cancelled,
        elapsed,
        0.0 if completed == 0 else elapsed / completed,
        peak_memory,
        _wilson(decoded, completed),
        _wilson(false_decodes, completed_noise),
        float(np.mean(minimum_gains)) if minimum_gains else 0.0,
        float(np.mean(erased_percents)) if erased_percents else 0.0,
        fading_equalized_trials,
        (
            float(np.mean(variation_confidences))
            if variation_confidences
            else 0.0
        ),
        float(np.mean(diversity_scores)) if diversity_scores else 0.0,
    )
    if event_callback is not None:
        event_callback("DEEP_VALIDATION_END", asdict(result))
    return result
