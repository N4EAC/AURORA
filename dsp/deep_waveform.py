"""Offline BPSK audio waveform support for Aurora Deep-mode research."""

from dataclasses import dataclass
import math

import numpy as np

from audio.buffer import AudioBuffer
from dsp.preamble import PREAMBLE_SYMBOL_COUNT, acquisition_symbols
from dsp.soft_decision import soft_demapping
from dsp.waveform import (
    WaveformDiagnostics,
    demodulate_audio,
    modulate_audio,
    root_raised_cosine_taps,
    samples_per_symbol,
)
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition


DEEP_SAMPLE_RATE = AURORA_ROBUST_MODE.audio_sample_rate
DEEP_SYMBOL_RATE = AURORA_ROBUST_MODE.symbol_rate
DEEP_PILOT_INTERVAL = 128
DEEP_PILOT_SYMBOL_COUNT = 16


@dataclass(frozen=True, slots=True)
class DeepWaveformResult:
    """Recovered soft bits and acquisition diagnostics for one hypothesis."""

    likelihoods: tuple[float, ...]
    diagnostics: WaveformDiagnostics
    clock_error_ppm: float
    frequency_hypothesis_hz: float
    acquisition_score: float
    pilot_quality: float
    residual_frequency_hz: float
    tracking_enabled: bool
    minimum_relative_gain: float = 1.0
    fade_depth_db: float = 0.0
    erased_symbol_percent: float = 0.0
    fading_equalization_enabled: bool = False
    channel_variation_confidence: float = 0.0
    acquisition_diversity_score: float = 0.0


def bits_to_bpsk(bits: tuple[int, ...] | list[int]) -> np.ndarray:
    """Map binary values to normalized real BPSK symbols."""
    values = np.asarray(bits, dtype=np.int8)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("Deep waveform bits must be a non-empty sequence")
    if np.any((values != 0) & (values != 1)):
        raise ValueError("Deep waveform input must contain only binary values")
    symbols = np.where(values == 0, 1.0, -1.0).astype(np.complex128)
    symbols.setflags(write=False)
    return symbols


def deep_pilot_symbols(
    symbol_count: int = DEEP_PILOT_SYMBOL_COUNT,
) -> np.ndarray:
    """Return the fixed research pilot group."""
    if not 0 < symbol_count <= PREAMBLE_SYMBOL_COUNT:
        raise ValueError("Pilot symbol count must fit within the preamble")
    pilots = acquisition_symbols()[:symbol_count].astype(np.complex128)
    pilots.setflags(write=False)
    return pilots


def multiplex_deep_pilots(
    data_symbols: np.ndarray,
    interval: int = DEEP_PILOT_INTERVAL,
    pilot_symbol_count: int = DEEP_PILOT_SYMBOL_COUNT,
) -> np.ndarray:
    """Insert a pilot group between fixed-size data blocks."""
    data = np.asarray(data_symbols, dtype=np.complex128)
    if data.ndim != 1 or len(data) == 0:
        raise ValueError("Deep pilot input must be a non-empty symbol sequence")
    if interval <= 0:
        raise ValueError("Pilot interval must be positive")
    parts: list[np.ndarray] = []
    for start in range(0, len(data), interval):
        parts.append(data[start : start + interval])
        if start + interval < len(data):
            parts.append(deep_pilot_symbols(pilot_symbol_count))
    result = np.concatenate(parts)
    result.setflags(write=False)
    return result


def deep_pilot_overhead(
    payload_symbol_count: int,
    interval: int = DEEP_PILOT_INTERVAL,
    pilot_symbol_count: int = DEEP_PILOT_SYMBOL_COUNT,
) -> int:
    """Return inserted pilot symbols for a known payload length."""
    if payload_symbol_count <= 0:
        raise ValueError("Payload symbol count must be positive")
    if interval <= 0:
        raise ValueError("Pilot interval must be positive")
    deep_pilot_symbols(pilot_symbol_count)
    groups = (payload_symbol_count - 1) // interval
    return groups * pilot_symbol_count


def modulate_deep_audio(
    bits: tuple[int, ...] | list[int],
    *,
    leading_silence_samples: int = 0,
    frequency_offset_hz: float = 0.0,
    pilots_enabled: bool = True,
    pilot_interval: int = DEEP_PILOT_INTERVAL,
    pilot_symbol_count: int = DEEP_PILOT_SYMBOL_COUNT,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> AudioBuffer:
    """Generate the provisional Deep research waveform without opening hardware."""
    symbols = bits_to_bpsk(bits)
    if pilots_enabled:
        symbols = multiplex_deep_pilots(
            symbols,
            pilot_interval,
            pilot_symbol_count,
        )
    return modulate_audio(
        symbols,
        mode,
        leading_silence_samples=leading_silence_samples,
        frequency_offset_hz=frequency_offset_hz,
    )


def _correct_clock(audio: AudioBuffer, clock_error_ppm: float) -> AudioBuffer:
    if clock_error_ppm == 0.0:
        return audio
    samples = np.asarray(audio.samples, dtype=np.float64)
    indices = np.arange(len(samples), dtype=np.float64)
    source_positions = indices / (1.0 + clock_error_ppm * 1e-6)
    corrected = np.interp(
        source_positions,
        indices,
        samples,
        left=0.0,
        right=0.0,
    )
    return AudioBuffer(corrected.astype(np.float32), audio.sample_rate)


def _analytic_signal(samples: np.ndarray) -> np.ndarray:
    """Return an FFT-derived analytic representation of real audio."""
    spectrum = np.fft.fft(samples)
    multiplier = np.zeros(len(samples), dtype=np.float64)
    multiplier[0] = 1.0
    if len(samples) % 2 == 0:
        multiplier[1 : len(samples) // 2] = 2.0
        multiplier[len(samples) // 2] = 1.0
    else:
        multiplier[1 : (len(samples) + 1) // 2] = 2.0
    return np.fft.ifft(spectrum * multiplier)


def _correct_frequency(audio: AudioBuffer, hypothesis_hz: float) -> AudioBuffer:
    if hypothesis_hz == 0.0:
        return audio
    samples = np.asarray(audio.samples, dtype=np.float64)
    indices = np.arange(len(samples), dtype=np.float64)
    shifted = _analytic_signal(samples) * np.exp(
        -2j * np.pi * hypothesis_hz * indices / audio.sample_rate
    )
    return AudioBuffer(shifted.real.astype(np.float32), audio.sample_rate)


def _separate_pilots(
    symbols: np.ndarray,
    payload_symbol_count: int,
    tracking_enabled: bool,
    pilot_interval: int = DEEP_PILOT_INTERVAL,
    pilot_symbol_count: int = DEEP_PILOT_SYMBOL_COUNT,
    symbol_rate: float = DEEP_SYMBOL_RATE,
) -> tuple[np.ndarray, float, float]:
    pilot = deep_pilot_symbols(pilot_symbol_count)
    pilot_starts: list[int] = []
    cursor = 0
    remaining = payload_symbol_count
    while remaining:
        block_size = min(pilot_interval, remaining)
        cursor += block_size
        remaining -= block_size
        if remaining:
            pilot_starts.append(cursor)
            cursor += len(pilot)

    working = symbols
    coarse_residual_hz = 0.0
    if tracking_enabled and pilot_starts:
        differential = 0.0j
        for start in pilot_starts:
            observed = symbols[start : start + len(pilot)] * np.conj(pilot)
            differential += np.vdot(observed[:-1], observed[1:])
        phase_step = float(np.angle(differential))
        coarse_residual_hz = phase_step * symbol_rate / (2.0 * np.pi)
        positions = np.arange(len(symbols), dtype=np.float64)
        working = symbols * np.exp(-1j * phase_step * positions)
    data_parts: list[np.ndarray] = []
    pilot_centers: list[float] = []
    pilot_phases: list[float] = []
    pilot_qualities: list[float] = []
    cursor = 0
    remaining = payload_symbol_count
    while remaining:
        block_size = min(pilot_interval, remaining)
        data_parts.append(working[cursor : cursor + block_size])
        cursor += block_size
        remaining -= block_size
        if remaining:
            received_pilot = working[cursor : cursor + len(pilot)]
            if len(received_pilot) != len(pilot):
                raise ValueError("Deep waveform ends within a pilot group")
            correlation = np.vdot(pilot, received_pilot)
            pilot_centers.append(cursor + (len(pilot) - 1) / 2.0)
            pilot_phases.append(float(np.angle(correlation)))
            pilot_qualities.append(float(abs(correlation) / len(pilot)))
            cursor += len(pilot)

    if not pilot_centers:
        data = np.concatenate(data_parts)
        return data, 0.0, 0.0

    phases = np.unwrap(np.asarray(pilot_phases))
    residual_hz = 0.0
    if len(phases) > 1:
        slope = float(np.polyfit(pilot_centers, phases, 1)[0])
        residual_hz = slope * symbol_rate / (2.0 * np.pi)
    if tracking_enabled:
        all_positions = np.arange(len(working), dtype=np.float64)
        correction_phase = np.interp(
            all_positions,
            pilot_centers,
            phases,
            left=phases[0],
            right=phases[-1],
        )
        corrected = working * np.exp(-1j * correction_phase)
        data_parts = []
        cursor = 0
        remaining = payload_symbol_count
        while remaining:
            block_size = min(pilot_interval, remaining)
            data_parts.append(corrected[cursor : cursor + block_size])
            cursor += block_size
            remaining -= block_size
            if remaining:
                cursor += len(pilot)
    data = np.concatenate(data_parts)
    return (
        data,
        float(np.mean(pilot_qualities)),
        coarse_residual_hz + residual_hz,
    )


def recover_deep_likelihoods(
    audio: AudioBuffer,
    payload_bit_count: int,
    *,
    clock_search_ppm: tuple[float, ...] = (0.0,),
    frequency_search_hz: tuple[float, ...] = (0.0,),
    acquisition_score_threshold: float = 3.0,
    noise_variance: float = 1.0,
    pilots_enabled: bool = True,
    tracking_enabled: bool = True,
    pilot_interval: int = DEEP_PILOT_INTERVAL,
    pilot_symbol_count: int = DEEP_PILOT_SYMBOL_COUNT,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> DeepWaveformResult:
    """Search clock hypotheses and return soft BPSK decisions."""
    if not clock_search_ppm:
        raise ValueError("Clock search grid must not be empty")
    if not frequency_search_hz:
        raise ValueError("Frequency search grid must not be empty")
    if noise_variance <= 0.0:
        raise ValueError("Noise variance must be positive")
    if acquisition_score_threshold <= 0.0:
        raise ValueError("Acquisition score threshold must be positive")

    best: DeepWaveformResult | None = None
    errors: list[ValueError] = []
    for clock_error_ppm in clock_search_ppm:
        clock_corrected = _correct_clock(audio, clock_error_ppm)
        for frequency_hypothesis_hz in frequency_search_hz:
            corrected = _correct_frequency(
                clock_corrected, frequency_hypothesis_hz
            )
            try:
                waveform_symbol_count = payload_bit_count
                if pilots_enabled:
                    waveform_symbol_count += deep_pilot_overhead(
                        payload_bit_count,
                        pilot_interval,
                        pilot_symbol_count,
                    )
                recovered = demodulate_audio(
                    corrected,
                    waveform_symbol_count,
                    mode,
                    sync_threshold=0.0,
                )
            except ValueError as error:
                errors.append(error)
                continue
            acquisition_score = (
                recovered.diagnostics.sync_metric * np.sqrt(PREAMBLE_SYMBOL_COUNT)
            )
            if acquisition_score < acquisition_score_threshold:
                errors.append(
                    ValueError(
                        f"Deep acquisition score {acquisition_score:.3f} "
                        "is below threshold"
                    )
                )
                continue
            payload_symbols = recovered.symbols
            pilot_quality = residual_hz = 0.0
            if pilots_enabled:
                payload_symbols, pilot_quality, residual_hz = _separate_pilots(
                    payload_symbols,
                    payload_bit_count,
                    tracking_enabled,
                    pilot_interval,
                    pilot_symbol_count,
                    mode.symbol_rate,
                )
            likelihoods = soft_demapping(
                payload_symbols,
                modulation="bpsk",
                noise_variance=noise_variance,
            )
            candidate = DeepWaveformResult(
                tuple(float(value) for value in likelihoods),
                recovered.diagnostics,
                float(clock_error_ppm),
                float(frequency_hypothesis_hz),
                float(acquisition_score),
                pilot_quality,
                residual_hz,
                tracking_enabled and pilots_enabled,
            )
            if (
                best is None
                or candidate.diagnostics.sync_metric > best.diagnostics.sync_metric
            ):
                best = candidate
    if best is None:
        detail = str(errors[-1]) if errors else "no hypotheses evaluated"
        raise ValueError(f"Deep waveform acquisition failed: {detail}")
    return best


def _known_symbol_geometry(
    payload_symbol_count: int,
    pilot_interval: int,
    pilot_symbol_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return preamble/pilot positions and their known symbols."""
    preamble = acquisition_symbols().astype(np.complex128)
    pilot = deep_pilot_symbols(pilot_symbol_count)
    positions: list[np.ndarray] = [np.arange(len(preamble))]
    references: list[np.ndarray] = [preamble]
    cursor = 0
    remaining = payload_symbol_count
    while remaining:
        block_size = min(pilot_interval, remaining)
        cursor += block_size
        remaining -= block_size
        if remaining:
            positions.append(
                len(preamble) + np.arange(cursor, cursor + len(pilot))
            )
            references.append(pilot)
            cursor += len(pilot)
    return np.concatenate(positions), np.concatenate(references)


def _known_symbol_groups(
    payload_symbol_count: int,
    pilot_interval: int,
    pilot_symbol_count: int,
) -> tuple[tuple[int, np.ndarray], ...]:
    """Return the preamble and time-separated pilots as acquisition groups."""
    preamble = acquisition_symbols().astype(np.complex128)
    pilot = deep_pilot_symbols(pilot_symbol_count)
    groups: list[tuple[int, np.ndarray]] = [(0, preamble)]
    cursor = len(preamble)
    remaining = payload_symbol_count
    while remaining:
        block_size = min(pilot_interval, remaining)
        cursor += block_size
        remaining -= block_size
        if remaining:
            groups.append((cursor, pilot))
            cursor += len(pilot)
    return tuple(groups)


def _normalized_group_metric(
    symbols: np.ndarray,
    final_start: int,
    groups: tuple[tuple[int, np.ndarray], ...],
) -> np.ndarray:
    """Combine time-separated known groups without coherent phase dependence."""
    combined = np.zeros(final_start + 1, dtype=np.float64)
    for offset, reference in groups:
        shifted = symbols[offset:]
        correlation = np.correlate(shifted, reference, mode="valid")[
            : final_start + 1
        ]
        energy = np.convolve(
            np.abs(shifted) ** 2,
            np.ones(len(reference)),
            mode="valid",
        )[: final_start + 1]
        combined += np.abs(correlation) / np.sqrt(
            np.maximum(energy * len(reference), np.finfo(float).tiny)
        )
    return combined / len(groups)


def _recovered_group_score(
    symbols: np.ndarray,
    groups: tuple[tuple[int, np.ndarray], ...],
) -> float:
    """Measure noncoherent agreement with known groups across one frame."""
    scores = []
    for offset, reference in groups:
        received = symbols[offset : offset + len(reference)]
        denominator = math.sqrt(
            max(
                float(np.sum(np.abs(received) ** 2)) * len(reference),
                np.finfo(float).tiny,
            )
        )
        scores.append(float(abs(np.vdot(reference, received)) / denominator))
    return float(np.mean(scores))


def _fading_weighted_symbols(
    symbols: np.ndarray,
    payload_symbol_count: int,
    *,
    erasure_gain_ratio: float,
    activation_gain_ratio: float,
    confidence_threshold: float,
    pilot_interval: int,
    pilot_symbol_count: int,
) -> tuple[np.ndarray, float, float, float, bool, float]:
    """Estimate pilot gain and reliability-weight symbols during proven fades."""
    preamble = acquisition_symbols().astype(np.complex128)
    pilot = deep_pilot_symbols(pilot_symbol_count)
    centers = [float((len(preamble) - 1) / 2.0)]
    preamble_observations = symbols[: len(preamble)] * np.conj(preamble)
    observation_groups = [preamble_observations]
    cursor = len(preamble)
    remaining = payload_symbol_count
    while remaining:
        block_size = min(pilot_interval, remaining)
        cursor += block_size
        remaining -= block_size
        if remaining:
            received = symbols[cursor : cursor + len(pilot)] * np.conj(pilot)
            observation_groups.append(received)
            centers.append(cursor + (len(pilot) - 1) / 2.0)
            cursor += len(pilot)

    raw_gain_values = np.asarray(
        [np.mean(group) for group in observation_groups],
        dtype=np.complex128,
    )
    estimate_variances = np.asarray(
        [
            max(
                float(np.mean(np.abs(group - np.mean(group)) ** 2)) / len(group),
                np.finfo(float).tiny,
            )
            for group in observation_groups
        ],
        dtype=np.float64,
    )
    smoothed_gain_values = raw_gain_values.copy()
    if len(raw_gain_values) > 2:
        for index in range(1, len(raw_gain_values) - 1):
            local_variances = estimate_variances[index - 1 : index + 2]
            weights = np.asarray((1.0, 2.0, 1.0)) / local_variances
            smoothed_gain_values[index] = np.sum(
                raw_gain_values[index - 1 : index + 2] * weights
            ) / np.sum(weights)
    adjacent_variance = estimate_variances[:-1] + estimate_variances[1:]
    normalized_changes = (
        np.abs(np.diff(smoothed_gain_values)) ** 2 / adjacent_variance
    )
    variation_confidence = (
        float(np.max(normalized_changes)) if len(normalized_changes) else 0.0
    )
    positions = np.arange(len(symbols), dtype=np.float64)
    interpolated = np.interp(
        positions, centers, raw_gain_values.real
    ) + 1j * np.interp(
        positions, centers, raw_gain_values.imag
    )
    magnitudes = np.abs(interpolated)
    reference_gain = max(
        float(np.median(np.abs(raw_gain_values))),
        np.finfo(float).tiny,
    )
    relative_gain = magnitudes / reference_gain
    weighted = symbols * np.conj(interpolated) / (reference_gain * reference_gain)
    erased = relative_gain < erasure_gain_ratio
    weighted[erased] = 0.0
    minimum_gain = float(np.min(relative_gain))
    fade_depth_db = float(-20.0 * np.log10(max(minimum_gain, 1e-12)))
    if (
        minimum_gain >= activation_gain_ratio
        or variation_confidence < confidence_threshold
    ):
        return (
            symbols,
            minimum_gain,
            fade_depth_db,
            0.0,
            False,
            variation_confidence,
        )
    erased_percent = float(100.0 * np.mean(erased))
    return (
        weighted,
        minimum_gain,
        fade_depth_db,
        erased_percent,
        True,
        variation_confidence,
    )


def _matched_baseband(
    audio: AudioBuffer,
    mode: ModeDefinition,
) -> np.ndarray:
    samples = np.asarray(audio.samples, dtype=np.float64)
    indices = np.arange(len(samples), dtype=np.float64)
    baseband = 2.0 * samples * np.exp(
        -2j
        * np.pi
        * mode.audio_carrier_hz
        * indices
        / audio.sample_rate
    )
    taps = root_raised_cosine_taps(
        samples_per_symbol(mode),
        mode.pulse_rolloff,
        mode.pulse_span_symbols,
    )
    return np.convolve(baseband, taps, mode="full")


def recover_deep_candidate_likelihoods(
    audio: AudioBuffer,
    payload_bit_count: int,
    *,
    clock_search_ppm: tuple[float, ...] = (0.0,),
    frequency_search_hz: tuple[float, ...] = (0.0,),
    residual_frequency_hz: tuple[float, ...] = tuple(
        np.arange(-0.03, 0.0301, 0.005)
    ),
    acquisition_peaks: int = 5,
    timing_step_samples: int = 16,
    decode_candidates: int = 3,
    fading_equalization: bool = False,
    erasure_gain_ratio: float = 0.0,
    fading_activation_gain_ratio: float = 0.6,
    fading_confidence_threshold: float = 1.0,
    acquisition_diversity: bool = False,
    pilot_interval: int = DEEP_PILOT_INTERVAL,
    pilot_symbol_count: int = DEEP_PILOT_SYMBOL_COUNT,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> tuple[DeepWaveformResult, ...]:
    """Return a bounded list ranked by coherent preamble-plus-pilot energy."""
    if min(acquisition_peaks, timing_step_samples, decode_candidates) <= 0:
        raise ValueError("Deep receiver search counts must be positive")
    if not 0.0 <= erasure_gain_ratio < 1.0:
        raise ValueError("Erasure gain ratio must be between zero and one")
    if not 0.0 <= fading_activation_gain_ratio <= 1.0:
        raise ValueError("Fading activation gain ratio must be between zero and one")
    if fading_confidence_threshold <= 0.0:
        raise ValueError("Fading confidence threshold must be positive")
    deep_pilot_overhead(
        payload_bit_count,
        pilot_interval,
        pilot_symbol_count,
    )
    ratio = samples_per_symbol(mode)
    waveform_count = (
        PREAMBLE_SYMBOL_COUNT
        + payload_bit_count
        + deep_pilot_overhead(
            payload_bit_count,
            pilot_interval,
            pilot_symbol_count,
        )
    )
    known_positions, known_reference = _known_symbol_geometry(
        payload_bit_count,
        pilot_interval,
        pilot_symbol_count,
    )
    known_groups = _known_symbol_groups(
        payload_bit_count,
        pilot_interval,
        pilot_symbol_count,
    )
    candidates: list[tuple[float, DeepWaveformResult]] = []

    for clock_ppm in clock_search_ppm:
        clock_corrected = _correct_clock(audio, clock_ppm)
        for coarse_hz in frequency_search_hz:
            corrected = _correct_frequency(clock_corrected, coarse_hz)
            matched = _matched_baseband(corrected, mode)
            raw_peaks: list[tuple[float, int]] = []
            preamble = acquisition_symbols().astype(np.complex128)
            for phase in range(ratio):
                symbols = matched[phase::ratio]
                final_start = len(symbols) - waveform_count
                if final_start < 0:
                    continue
                if acquisition_diversity:
                    metrics = _normalized_group_metric(
                        symbols,
                        final_start,
                        known_groups,
                    )
                else:
                    correlation = np.correlate(
                        symbols, preamble, mode="valid"
                    )[: final_start + 1]
                    energy = np.convolve(
                        np.abs(symbols) ** 2,
                        np.ones(len(preamble)),
                        mode="valid",
                    )[: final_start + 1]
                    metrics = np.abs(correlation) / np.sqrt(
                        np.maximum(
                            energy * len(preamble),
                            np.finfo(float).tiny,
                        )
                    )
                index = int(np.argmax(metrics))
                raw_peaks.append(
                    (float(metrics[index]), phase + index * ratio)
                )
            raw_peaks.sort(reverse=True)
            peak_starts: list[int] = []
            for _, start in raw_peaks:
                if all(abs(start - selected) > ratio for selected in peak_starts):
                    peak_starts.append(start)
                if len(peak_starts) == acquisition_peaks:
                    break

            for peak_start in peak_starts:
                first = max(0, peak_start - ratio // 2)
                last = peak_start + ratio // 2
                for start in range(first, last + 1, timing_step_samples):
                    recovered = matched[
                        start : start + waveform_count * ratio : ratio
                    ]
                    if len(recovered) != waveform_count:
                        continue
                    observations = (
                        recovered[known_positions] * np.conj(known_reference)
                    )
                    correlations = [
                        np.sum(
                            observations
                            * np.exp(
                                -2j
                                * np.pi
                                * residual_hz
                                * known_positions
                                / mode.symbol_rate
                            )
                        )
                        for residual_hz in residual_frequency_hz
                    ]
                    best_index = int(np.argmax(np.abs(correlations)))
                    fine_hz = residual_frequency_hz[best_index]
                    correlation = correlations[best_index]
                    phase = float(np.angle(correlation))
                    positions = np.arange(waveform_count, dtype=np.float64)
                    carrier_corrected = recovered * np.exp(
                        -1j
                        * (
                            2.0
                            * np.pi
                            * fine_hz
                            * positions
                            / mode.symbol_rate
                            + phase
                        )
                    )
                    diversity_score = _recovered_group_score(
                        carrier_corrected,
                        known_groups,
                    )
                    minimum_gain = 1.0
                    fade_depth_db = erased_percent = 0.0
                    fading_equalization_applied = False
                    variation_confidence = 0.0
                    if fading_equalization:
                        (
                            carrier_corrected,
                            minimum_gain,
                            fade_depth_db,
                            erased_percent,
                            fading_equalization_applied,
                            variation_confidence,
                        ) = _fading_weighted_symbols(
                            carrier_corrected,
                            payload_bit_count,
                            erasure_gain_ratio=erasure_gain_ratio,
                            activation_gain_ratio=fading_activation_gain_ratio,
                            confidence_threshold=fading_confidence_threshold,
                            pilot_interval=pilot_interval,
                            pilot_symbol_count=pilot_symbol_count,
                        )
                    payload, pilot_quality, _ = _separate_pilots(
                        carrier_corrected[PREAMBLE_SYMBOL_COUNT:],
                        payload_bit_count,
                        False,
                        pilot_interval,
                        pilot_symbol_count,
                        mode.symbol_rate,
                    )
                    likelihoods = soft_demapping(payload, modulation="bpsk")
                    coherent_score = float(
                        abs(correlation) / len(known_positions)
                    )
                    result = DeepWaveformResult(
                        tuple(float(value) for value in likelihoods),
                        WaveformDiagnostics(
                            True,
                            coherent_score,
                            coarse_hz + fine_hz,
                            start,
                        ),
                        float(clock_ppm),
                        float(coarse_hz),
                        coherent_score,
                        pilot_quality,
                        float(fine_hz),
                        True,
                        minimum_gain,
                        fade_depth_db,
                        erased_percent,
                        fading_equalization_applied,
                        variation_confidence,
                        diversity_score,
                    )
                    ranking_score = (
                        diversity_score
                        if acquisition_diversity
                        else coherent_score
                    )
                    candidates.append((ranking_score, result))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return tuple(result for _, result in candidates[:decode_candidates])
