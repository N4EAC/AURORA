"""Comparative −30 dB acquisition study without a claimed Aurora protocol."""

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
import argparse
import math
import time

import numpy as np

from audio.buffer import AudioBuffer
from dsp.audio_channel import AudioChannelConfig, apply_audio_channel, reference_noise_variance
from dsp.extreme_waveforms import (
    EXTREME_SAMPLE_RATE,
    EXTREME_SAMPLES_PER_SYMBOL,
    EXTREME_SYMBOL_RATE,
    generate_acquisition_audio,
    search_acquisition,
)
from dsp.waveform import occupied_bandwidth_hz


EventCallback = Callable[[str, dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class ExtremeChannelProfile:
    """Named deterministic impairment selection for acquisition research."""

    name: str
    channel: AudioChannelConfig = AudioChannelConfig(snr_db=None)


AWGN_EXTREME_PROFILE = ExtremeChannelProfile("AWGN reference")
EXTREME_CHANNEL_PROFILES = {
    profile.name: profile
    for profile in (
        AWGN_EXTREME_PROFILE,
        ExtremeChannelProfile(
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
        ExtremeChannelProfile(
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
        ExtremeChannelProfile(
            "Fading only",
            AudioChannelConfig(
                snr_db=None,
                fading_depth=0.65,
                fading_cycles_per_frame=2.0,
            ),
        ),
        ExtremeChannelProfile(
            "Multipath only",
            AudioChannelConfig(
                snr_db=None,
                multipath_delay_ms=5.0,
                multipath_gain=0.45,
            ),
        ),
        ExtremeChannelProfile(
            "Clock error only",
            AudioChannelConfig(snr_db=None, clock_error_ppm=75.0),
        ),
        ExtremeChannelProfile(
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
class IdealCodeBudget:
    """Information-rate budget only; this is not an encoder or decoder."""

    coded_bits: int = 1_024
    information_bits: int = 128

    def __post_init__(self) -> None:
        if self.coded_bits <= 0 or not 0 < self.information_bits < self.coded_bits:
            raise ValueError("Ideal code dimensions are invalid")

    @property
    def rate(self) -> float:
        """Return the assumed information-to-coded-bit ratio."""
        return self.information_bits / self.coded_bits

    @property
    def information_rate_bps(self) -> float:
        """Return assumed information rate for one coded bit per symbol."""
        return EXTREME_SYMBOL_RATE * self.rate


@dataclass(frozen=True, slots=True)
class ExtremeStudyConfig:
    """Deterministic acquisition-study configuration."""

    snr_db: float = -30.0
    reference_bandwidth_hz: float = 2_500.0
    seeds: tuple[int, ...] = (2026, 2027)
    noise_trials: int = 8
    modulations: tuple[str, ...] = ("bpsk", "4gfsk")
    profile: ExtremeChannelProfile = AWGN_EXTREME_PROFILE
    leading_silence_samples: int = 731
    injected_frequency_offset_hz: float = 0.0
    frequency_search_hz: tuple[float, ...] = (-0.5, 0.0, 0.5)
    clock_search_ppm: tuple[float, ...] = (0.0,)
    detection_peak_to_median: float = 5.0
    timing_tolerance_symbols: float = 0.10
    code_budget: IdealCodeBudget = IdealCodeBudget()

    def __post_init__(self) -> None:
        if not self.seeds:
            raise ValueError("Extreme study requires random seeds")
        if self.reference_bandwidth_hz <= 0.0:
            raise ValueError("Reference bandwidth must be positive")
        if self.noise_trials <= 0:
            raise ValueError("Extreme study requires noise-only trials")
        if not self.modulations or any(
            modulation not in ("bpsk", "4gfsk") for modulation in self.modulations
        ):
            raise ValueError("Extreme study modulation selection is invalid")
        if self.leading_silence_samples < 0 or self.timing_tolerance_symbols <= 0.0:
            raise ValueError("Timing values must not be negative")
        if self.detection_peak_to_median <= 1.0:
            raise ValueError("Detection ratio must exceed one")
        if not self.clock_search_ppm:
            raise ValueError("Clock search grid must not be empty")


@dataclass(frozen=True, slots=True)
class CandidateStudyResult:
    """Acquisition and false-alarm outcomes for one candidate waveform."""

    modulation: str
    trials: int
    noise_trials: int
    detected_trials: int
    timing_located_trials: int
    frequency_matched_trials: int
    clock_matched_trials: int
    acquired_trials: int
    false_alarms: int
    mean_peak_to_median: float
    mean_noise_peak_to_median: float
    mean_absolute_timing_error_samples: float
    percentile_95_timing_error_samples: float
    maximum_timing_error_samples: float
    mean_peak_curvature: float
    mean_clock_error_ppm: float
    mean_absolute_clock_error_ppm: float
    mean_clock_metric_margin: float
    occupied_bandwidth_hz: float
    elapsed_seconds: float
    cancelled: bool = False

    @property
    def acquisition_rate_percent(self) -> float:
        """Return complete acquisition rate for completed signal trials."""
        return (
            0.0 if self.trials == 0 else 100.0 * self.acquired_trials / self.trials
        )

    @property
    def false_alarm_rate_percent(self) -> float:
        """Return false alarms as a percentage of completed noise trials."""
        return (
            0.0
            if self.noise_trials == 0
            else 100.0 * self.false_alarms / self.noise_trials
        )

    @property
    def acquisition_confidence_95(self) -> tuple[float, float]:
        """Return Wilson 95% bounds for complete acquisition percentage."""
        return _wilson_interval(self.acquired_trials, self.trials)

    @property
    def false_alarm_confidence_95(self) -> tuple[float, float]:
        """Return Wilson 95% bounds for false-alarm percentage."""
        return _wilson_interval(self.false_alarms, self.noise_trials)


@dataclass(frozen=True, slots=True)
class ExtremeStudyResult:
    """Capacity budget and candidate acquisition results."""

    capacity_bps: float
    assumed_information_rate_bps: float
    information_ebn0_db: float
    results: tuple[CandidateStudyResult, ...]
    profile_name: str
    cancelled: bool
    measurement_domain: str = "extreme_research"


@dataclass(frozen=True, slots=True)
class ClockSweepPoint:
    """One injected clock error and its 4-GFSK acquisition result."""

    injected_clock_error_ppm: float
    result: CandidateStudyResult


@dataclass(frozen=True, slots=True)
class ClockSweepResult:
    """Ordered clock-error study points and cancellation state."""

    points: tuple[ClockSweepPoint, ...]
    cancelled: bool
    elapsed_seconds: float
    measurement_domain: str = "extreme_research"


def awgn_capacity_bps(bandwidth_hz: float, snr_db: float) -> float:
    """Return ideal real-AWGN Shannon capacity in bits per second."""
    if bandwidth_hz <= 0.0:
        raise ValueError("Bandwidth must be positive")
    return bandwidth_hz * math.log2(1.0 + 10.0 ** (snr_db / 10.0))


def information_ebn0_db(
    snr_db: float, reference_bandwidth_hz: float, information_rate_bps: float
) -> float:
    """Convert reference-bandwidth SNR to information-bit Eb/N0."""
    if reference_bandwidth_hz <= 0.0 or information_rate_bps <= 0.0:
        raise ValueError("Bandwidth and information rate must be positive")
    return snr_db + 10.0 * math.log10(
        reference_bandwidth_hz / information_rate_bps
    )


def _wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    if trials <= 0 or not 0 <= successes <= trials:
        return 0.0, 0.0
    z = 1.959963984540054
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    margin = z * math.sqrt(
        proportion * (1.0 - proportion) / trials
        + z * z / (4.0 * trials * trials)
    ) / denominator
    return (
        100.0 * max(0.0, center - margin),
        100.0 * min(1.0, center + margin),
    )


def _emit(callback: EventCallback | None, event: str, **fields: object) -> None:
    if callback is not None:
        callback(event, fields)


def _noise_only_audio(
    clean: AudioBuffer,
    config: ExtremeStudyConfig,
    random: np.random.Generator,
) -> AudioBuffer:
    signal = np.asarray(clean.samples, dtype=np.float64)
    variance = reference_noise_variance(
        float(np.mean(signal * signal)),
        config.snr_db,
        clean.sample_rate,
        config.reference_bandwidth_hz,
    )
    noise = random.normal(0.0, math.sqrt(variance), len(signal))
    noise_audio = AudioBuffer(noise.astype(np.float32), clean.sample_rate)
    profile_channel = replace(
        config.profile.channel,
        snr_db=None,
        reference_bandwidth_hz=config.reference_bandwidth_hz,
    )
    return apply_audio_channel(noise_audio, profile_channel, random)


def _frequency_tolerance(config: ExtremeStudyConfig) -> float:
    alternatives = [
        abs(value - config.injected_frequency_offset_hz)
        for value in config.frequency_search_hz
        if value != config.injected_frequency_offset_hz
    ]
    return 0.01 if not alternatives else max(0.01, min(alternatives) / 2.0)


def _clock_tolerance(config: ExtremeStudyConfig) -> float:
    injected = config.profile.channel.clock_error_ppm
    alternatives = [
        abs(value - injected)
        for value in config.clock_search_ppm
        if value != injected
    ]
    return 0.01 if not alternatives else max(0.01, min(alternatives) / 2.0)


def _study_candidate(
    modulation: str,
    config: ExtremeStudyConfig,
    should_continue: Callable[[], bool] | None,
) -> CandidateStudyResult:
    clean = generate_acquisition_audio(
        modulation,
        leading_silence_samples=config.leading_silence_samples,
        frequency_offset_hz=config.injected_frequency_offset_hz,
    )
    channel = replace(
        config.profile.channel,
        snr_db=config.snr_db,
        reference_bandwidth_hz=config.reference_bandwidth_hz,
    )
    acquired = 0
    detected_trials = 0
    timing_located_trials = 0
    frequency_matched_trials = 0
    clock_matched_trials = 0
    false_alarms = 0
    signal_ratios: list[float] = []
    noise_ratios: list[float] = []
    timing_errors: list[float] = []
    peak_curvatures: list[float] = []
    clock_estimates: list[float] = []
    clock_errors: list[float] = []
    clock_margins: list[float] = []
    completed_signal_trials = 0
    completed_noise_trials = 0
    cancelled = False
    started = time.perf_counter()
    for seed in config.seeds:
        if should_continue is not None and not should_continue():
            cancelled = True
            break
        impaired = apply_audio_channel(clean, channel, np.random.default_rng(seed))
        acquisition = search_acquisition(
            impaired,
            modulation,
            frequency_search_hz=config.frequency_search_hz,
            clock_search_ppm=config.clock_search_ppm,
        )
        signal_ratios.append(acquisition.peak_to_median)
        completed_signal_trials += 1
        injected_clock_ppm = config.profile.channel.clock_error_ppm
        expected_start = config.leading_silence_samples / (
            1.0 + injected_clock_ppm * 1e-6
        )
        timing_error = abs(acquisition.refined_sample_index - expected_start)
        timing_errors.append(timing_error)
        peak_curvatures.append(acquisition.peak_curvature)
        located = (
            timing_error
            <= config.timing_tolerance_symbols * EXTREME_SAMPLES_PER_SYMBOL
        )
        frequency_found = math.isclose(
            acquisition.frequency_offset_hz,
            config.injected_frequency_offset_hz,
            abs_tol=_frequency_tolerance(config),
        )
        clock_found = math.isclose(
            acquisition.clock_error_ppm,
            injected_clock_ppm,
            abs_tol=_clock_tolerance(config),
        )
        clock_estimates.append(acquisition.clock_error_ppm)
        clock_errors.append(abs(acquisition.clock_error_ppm - injected_clock_ppm))
        clock_margins.append(acquisition.clock_metric_margin)
        detected = acquisition.peak_to_median >= config.detection_peak_to_median
        detected_trials += int(detected)
        timing_located_trials += int(located)
        frequency_matched_trials += int(frequency_found)
        clock_matched_trials += int(clock_found)
        if located and frequency_found and clock_found and detected:
            acquired += 1

    for trial_index in range(config.noise_trials):
        if cancelled or (should_continue is not None and not should_continue()):
            cancelled = True
            break
        noise_seed = config.seeds[0] + 1_000_000 + trial_index
        noise_audio = _noise_only_audio(
            clean, config, np.random.default_rng(noise_seed)
        )
        noise_result = search_acquisition(
            noise_audio,
            modulation,
            frequency_search_hz=config.frequency_search_hz,
            clock_search_ppm=config.clock_search_ppm,
        )
        noise_ratios.append(noise_result.peak_to_median)
        completed_noise_trials += 1
        if noise_result.peak_to_median >= config.detection_peak_to_median:
            false_alarms += 1
    return CandidateStudyResult(
        modulation=modulation.upper(),
        trials=completed_signal_trials,
        noise_trials=completed_noise_trials,
        detected_trials=detected_trials,
        timing_located_trials=timing_located_trials,
        frequency_matched_trials=frequency_matched_trials,
        clock_matched_trials=clock_matched_trials,
        acquired_trials=acquired,
        false_alarms=false_alarms,
        mean_peak_to_median=(float(np.mean(signal_ratios)) if signal_ratios else 0.0),
        mean_noise_peak_to_median=(
            float(np.mean(noise_ratios)) if noise_ratios else 0.0
        ),
        mean_absolute_timing_error_samples=(
            float(np.mean(timing_errors)) if timing_errors else 0.0
        ),
        percentile_95_timing_error_samples=(
            float(np.percentile(timing_errors, 95.0)) if timing_errors else 0.0
        ),
        maximum_timing_error_samples=(
            float(np.max(timing_errors)) if timing_errors else 0.0
        ),
        mean_peak_curvature=(
            float(np.mean(peak_curvatures)) if peak_curvatures else 0.0
        ),
        mean_clock_error_ppm=(
            float(np.mean(clock_estimates)) if clock_estimates else 0.0
        ),
        mean_absolute_clock_error_ppm=(
            float(np.mean(clock_errors)) if clock_errors else 0.0
        ),
        mean_clock_metric_margin=(
            float(np.mean(clock_margins)) if clock_margins else 0.0
        ),
        occupied_bandwidth_hz=occupied_bandwidth_hz(clean),
        elapsed_seconds=time.perf_counter() - started,
        cancelled=cancelled,
    )


def run_extreme_study(
    config: ExtremeStudyConfig = ExtremeStudyConfig(),
    *,
    event_callback: EventCallback | None = None,
    should_continue: Callable[[], bool] | None = None,
) -> ExtremeStudyResult:
    """Compare acquisition only; no ideal-code payload decode is attempted."""
    _emit(
        event_callback,
        "EXTREME_STUDY_START",
        measurement_domain="extreme_research",
        snr_db=config.snr_db,
        reference_bandwidth_hz=config.reference_bandwidth_hz,
        seeds=config.seeds,
        noise_trials=config.noise_trials,
        profile_name=config.profile.name,
        clock_search_ppm=config.clock_search_ppm,
        channel_config=asdict(config.profile.channel),
        ideal_code_rate=config.code_budget.rate,
        ideal_code_implemented=False,
    )
    completed_results: list[CandidateStudyResult] = []
    for modulation in config.modulations:
        result = _study_candidate(modulation, config, should_continue)
        completed_results.append(result)
        if result.cancelled:
            break
    results = tuple(completed_results)
    study = ExtremeStudyResult(
        capacity_bps=awgn_capacity_bps(
            config.reference_bandwidth_hz, config.snr_db
        ),
        assumed_information_rate_bps=config.code_budget.information_rate_bps,
        information_ebn0_db=information_ebn0_db(
            config.snr_db,
            config.reference_bandwidth_hz,
            config.code_budget.information_rate_bps,
        ),
        results=results,
        profile_name=config.profile.name,
        cancelled=any(result.cancelled for result in results),
    )
    for result in results:
        _emit(
            event_callback,
            "EXTREME_STUDY_CANDIDATE",
            measurement_domain=study.measurement_domain,
            modulation=result.modulation,
            trials=result.trials,
            noise_trials=result.noise_trials,
            detected_trials=result.detected_trials,
            timing_located_trials=result.timing_located_trials,
            frequency_matched_trials=result.frequency_matched_trials,
            clock_matched_trials=result.clock_matched_trials,
            acquired_trials=result.acquired_trials,
            false_alarms=result.false_alarms,
            mean_peak_to_median=result.mean_peak_to_median,
            mean_noise_peak_to_median=result.mean_noise_peak_to_median,
            mean_absolute_timing_error_samples=(
                result.mean_absolute_timing_error_samples
            ),
            percentile_95_timing_error_samples=(
                result.percentile_95_timing_error_samples
            ),
            maximum_timing_error_samples=result.maximum_timing_error_samples,
            mean_peak_curvature=result.mean_peak_curvature,
            mean_clock_error_ppm=result.mean_clock_error_ppm,
            mean_absolute_clock_error_ppm=result.mean_absolute_clock_error_ppm,
            mean_clock_metric_margin=result.mean_clock_metric_margin,
            occupied_bandwidth_hz=result.occupied_bandwidth_hz,
            payload_decode_attempted=False,
            profile_name=study.profile_name,
            acquisition_confidence_95=result.acquisition_confidence_95,
            false_alarm_confidence_95=result.false_alarm_confidence_95,
            cancelled=result.cancelled,
        )
    _emit(
        event_callback,
        "EXTREME_STUDY_END",
        measurement_domain=study.measurement_domain,
        capacity_bps=study.capacity_bps,
        assumed_information_rate_bps=study.assumed_information_rate_bps,
        information_ebn0_db=study.information_ebn0_db,
        over_the_air_protocol=False,
        profile_name=study.profile_name,
        cancelled=study.cancelled,
    )
    return study


def run_clock_ppm_sweep(
    config: ExtremeStudyConfig,
    ppm_values: tuple[float, ...],
    *,
    event_callback: EventCallback | None = None,
    should_continue: Callable[[], bool] | None = None,
) -> ClockSweepResult:
    """Run cancellable 4-GFSK acquisition studies across injected clock errors."""
    if not ppm_values:
        raise ValueError("Clock sweep requires injected ppm values")
    started = time.perf_counter()
    points: list[ClockSweepPoint] = []
    cancelled = False
    for ppm in ppm_values:
        if should_continue is not None and not should_continue():
            cancelled = True
            break
        profile = ExtremeChannelProfile(
            f"Clock sweep {ppm:+g} ppm",
            replace(config.profile.channel, clock_error_ppm=ppm),
        )
        point_config = replace(
            config,
            profile=profile,
            modulations=("4gfsk",),
        )
        study = run_extreme_study(
            point_config,
            event_callback=event_callback,
            should_continue=should_continue,
        )
        if study.results:
            point = ClockSweepPoint(ppm, study.results[0])
            points.append(point)
            _emit(
                event_callback,
                "EXTREME_CLOCK_SWEEP_POINT",
                measurement_domain="extreme_research",
                injected_clock_error_ppm=ppm,
                selected_clock_error_ppm=point.result.mean_clock_error_ppm,
                mean_absolute_clock_error_ppm=(
                    point.result.mean_absolute_clock_error_ppm
                ),
                acquired_trials=point.result.acquired_trials,
                trials=point.result.trials,
                clock_matched_trials=point.result.clock_matched_trials,
                false_alarms=point.result.false_alarms,
                noise_trials=point.result.noise_trials,
            )
        if study.cancelled:
            cancelled = True
            break
    return ClockSweepResult(
        tuple(points),
        cancelled,
        time.perf_counter() - started,
    )


def main() -> int:
    """Run and log the conservative default extreme acquisition study."""
    parser = argparse.ArgumentParser(description="Aurora extreme acquisition research")
    parser.add_argument("--snr-db", type=float, default=-30.0)
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--noise-trials", type=int, default=8)
    parser.add_argument(
        "--modulation",
        choices=("bpsk", "4gfsk", "all"),
        default="4gfsk",
    )
    parser.add_argument(
        "--profile",
        choices=tuple(EXTREME_CHANNEL_PROFILES),
        default=AWGN_EXTREME_PROFILE.name,
    )
    parser.add_argument(
        "--clock-search-ppm",
        type=float,
        nargs="+",
        default=None,
    )
    parser.add_argument("--ppm-sweep", action="store_true")
    arguments = parser.parse_args()
    if arguments.trials <= 0:
        parser.error("--trials must be positive")
    if arguments.noise_trials <= 0:
        parser.error("--noise-trials must be positive")

    from config import SETTINGS
    from util.session_debug_log import SessionDebugLog

    seeds = tuple(2026 + index for index in range(arguments.trials))
    modulations = (
        ("bpsk", "4gfsk")
        if arguments.modulation == "all"
        else (arguments.modulation,)
    )
    standard_ppm_grid = (-100.0, -75.0, -50.0, -20.0, 0.0, 20.0, 50.0, 75.0, 100.0)
    clock_search_ppm = (
        tuple(arguments.clock_search_ppm)
        if arguments.clock_search_ppm is not None
        else (standard_ppm_grid if arguments.ppm_sweep else (0.0,))
    )
    config = ExtremeStudyConfig(
        snr_db=arguments.snr_db,
        seeds=seeds,
        noise_trials=arguments.noise_trials,
        modulations=modulations,
        profile=EXTREME_CHANNEL_PROFILES[arguments.profile],
        clock_search_ppm=clock_search_ppm,
        frequency_search_hz=((0.0,) if arguments.ppm_sweep else (-0.5, 0.0, 0.5)),
    )
    with SessionDebugLog(SETTINGS.log_directory, "0.4.0-dev") as session_log:
        event_callback = lambda event, fields: session_log.record(event, **fields)
        if arguments.ppm_sweep:
            sweep = run_clock_ppm_sweep(
                config,
                standard_ppm_grid,
                event_callback=event_callback,
            )
        else:
            result = run_extreme_study(config, event_callback=event_callback)
    if arguments.ppm_sweep:
        print(f"extreme_research clock sweep: {len(sweep.points)} points")
        for point in sweep.points:
            candidate = point.result
            print(
                f"{point.injected_clock_error_ppm:+g} ppm: acquisition "
                f"{candidate.acquired_trials}/{candidate.trials}, clock "
                f"{candidate.clock_matched_trials}/{candidate.trials}, selected "
                f"{candidate.mean_clock_error_ppm:+.1f} ppm"
            )
        return 0
    print(
        f"extreme_research: capacity={result.capacity_bps:.3f} bps, "
        f"assumed_rate={result.assumed_information_rate_bps:.3f} bps, "
        f"profile={result.profile_name}"
    )
    for candidate in result.results:
        print(
            f"{candidate.modulation}: acquisition "
            f"{candidate.acquired_trials}/{candidate.trials}, false alarms "
            f"{candidate.false_alarms}/{candidate.noise_trials}, detected "
            f"{candidate.detected_trials}/{candidate.trials}, timing "
            f"{candidate.timing_located_trials}/{candidate.trials}, frequency "
            f"{candidate.frequency_matched_trials}/{candidate.trials}, "
            f"timing MAE={candidate.mean_absolute_timing_error_samples:.1f} samples, "
            f"bandwidth={candidate.occupied_bandwidth_hz:.1f} Hz, "
            f"acquisition CI95={candidate.acquisition_confidence_95}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
