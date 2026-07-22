"""Simulation-only controller for the first Aurora operator iteration."""

from collections.abc import Callable
from dataclasses import dataclass
import math
import time

import numpy as np
from numpy.typing import NDArray

from dsp import decode_soft_symbols, encode_payload
from dsp.symbol_mapper import demap_symbols


@dataclass(frozen=True, slots=True)
class ChannelPreset:
    """Repeatable symbol-channel conditions for an operator test."""

    name: str
    snr_db: float
    frequency_offset_hz: float


CHANNEL_PRESETS = {
    "Clean": ChannelPreset("Clean", 30.0, 0.0),
    "Moderate HF": ChannelPreset("Moderate HF", 8.0, 0.05),
    "Weak Signal": ChannelPreset("Weak Signal", 2.0, 0.10),
    "Severe": ChannelPreset("Severe", -2.0, 0.25),
}


@dataclass(frozen=True, slots=True)
class ChannelImpairments:
    """Deterministic symbol-domain approximations of selected HF impairments."""

    name: str = "AWGN only"
    fading_depth: float = 0.0
    fading_cycles_per_frame: float = 0.0
    multipath_delay_symbols: int = 0
    multipath_gain: float = 0.0
    impulse_probability: float = 0.0
    impulse_scale: float = 0.0
    impulse_burst_symbols: int = 1
    phase_drift_radians: float = 0.0
    timing_offset_symbols: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.fading_depth < 1.0:
            raise ValueError("Fading depth must be between 0 and 1")
        if self.fading_cycles_per_frame < 0.0:
            raise ValueError("Fading cycles must not be negative")
        if self.multipath_delay_symbols < 0 or self.multipath_gain < 0.0:
            raise ValueError("Multipath delay and gain must not be negative")
        if not 0.0 <= self.impulse_probability <= 1.0:
            raise ValueError("Impulse probability must be between 0 and 1")
        if self.impulse_scale < 0.0:
            raise ValueError("Impulse scale must not be negative")
        if self.impulse_burst_symbols <= 0:
            raise ValueError("Impulse burst length must be positive")
        if not 0.0 <= self.timing_offset_symbols < 1.0:
            raise ValueError("Timing offset must be between 0 and 1 symbol")

    @property
    def measurement_domain(self) -> str:
        """Return the session-log domain identifier for this configuration."""
        return "symbol_awgn" if self.name == "AWGN only" else "symbol_hf_sim"

    def log_fields(self) -> dict[str, str | float | int]:
        """Return explicit structured fields for session logging."""
        return {
            "channel_profile": self.name,
            "fading_depth": self.fading_depth,
            "fading_cycles_per_frame": self.fading_cycles_per_frame,
            "fading_phase_policy": (
                "seeded_random_per_frame"
                if self.fading_depth > 0.0
                else "not_applicable"
            ),
            "multipath_delay_symbols": self.multipath_delay_symbols,
            "multipath_gain": self.multipath_gain,
            "impulse_probability": self.impulse_probability,
            "impulse_scale": self.impulse_scale,
            "impulse_burst_symbols": self.impulse_burst_symbols,
            "phase_drift_radians": self.phase_drift_radians,
            "timing_offset_symbols": self.timing_offset_symbols,
        }


AWGN_IMPAIRMENTS = ChannelImpairments()
CHANNEL_IMPAIRMENT_PROFILES = {
    AWGN_IMPAIRMENTS.name: AWGN_IMPAIRMENTS,
    "Moderate HF simulation": ChannelImpairments(
        name="Moderate HF simulation",
        fading_depth=0.25,
        fading_cycles_per_frame=0.75,
        multipath_delay_symbols=1,
        multipath_gain=0.15,
        impulse_probability=0.002,
        impulse_scale=4.0,
        phase_drift_radians=0.35,
        timing_offset_symbols=0.08,
    ),
    "Severe HF simulation": ChannelImpairments(
        name="Severe HF simulation",
        fading_depth=0.55,
        fading_cycles_per_frame=1.5,
        multipath_delay_symbols=2,
        multipath_gain=0.35,
        impulse_probability=0.01,
        impulse_scale=8.0,
        phase_drift_radians=1.0,
        timing_offset_symbols=0.20,
    ),
    "Fading only": ChannelImpairments(
        name="Fading only",
        fading_depth=0.55,
        fading_cycles_per_frame=1.5,
    ),
    "Multipath only": ChannelImpairments(
        name="Multipath only",
        multipath_delay_symbols=2,
        multipath_gain=0.35,
    ),
    "Impulsive noise only": ChannelImpairments(
        name="Impulsive noise only",
        impulse_probability=0.01,
        impulse_scale=8.0,
    ),
    "Impulsive bursts only": ChannelImpairments(
        name="Impulsive bursts only",
        impulse_probability=0.002,
        impulse_scale=8.0,
        impulse_burst_symbols=5,
    ),
    "Phase drift only": ChannelImpairments(
        name="Phase drift only",
        phase_drift_radians=1.0,
    ),
    "Timing offset only": ChannelImpairments(
        name="Timing offset only",
        timing_offset_symbols=0.20,
    ),
}


@dataclass(frozen=True, slots=True)
class SimulationDiagnostics:
    """Display values produced by the synthetic test signal."""

    synchronized: bool
    snr_db: float
    frequency_offset_hz: float
    timing_offset: float
    crc_status: str
    fec_status: str


@dataclass(frozen=True, slots=True)
class LocalTestResult:
    """Result of a local symbol-domain Aurora codec test."""

    transmitted_text: str
    received_text: str
    modulation: str
    diagnostics: SimulationDiagnostics


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Aggregate results from repeated impaired codec frames."""

    preset_name: str
    modulation: str
    snr_db: float
    frequency_offset_hz: float
    frame_count: int
    successful_frames: int
    channel_bit_errors: int
    corrected_bit_errors: int
    elapsed_seconds: float
    total_coded_bits: int = 0
    delivered_payload_bits: int = 0
    simulated_airtime_seconds: float = 0.0
    reference_bandwidth_hz: float | None = None
    symbol_rate: float = 3_000.0
    esn0_db: float | None = None
    cancelled: bool = False
    impairments: ChannelImpairments = AWGN_IMPAIRMENTS
    interleaver_columns: int | None = None

    @property
    def failed_frames(self) -> int:
        """Return the number of frames that failed decoding or CRC."""
        return self.frame_count - self.successful_frames

    @property
    def success_rate(self) -> float:
        """Return the percentage of successfully recovered frames."""
        if self.frame_count == 0:
            return 0.0
        return 100.0 * self.successful_frames / self.frame_count

    @property
    def average_frame_ms(self) -> float:
        """Return average processing time per frame in milliseconds."""
        if self.frame_count == 0:
            return 0.0
        return 1_000.0 * self.elapsed_seconds / self.frame_count

    @property
    def channel_ber(self) -> float:
        """Return pre-FEC hard-decision channel bit-error rate."""
        if self.total_coded_bits == 0:
            return 0.0
        return self.channel_bit_errors / self.total_coded_bits

    @property
    def net_throughput_bps(self) -> float:
        """Return successfully delivered payload bits per simulated second."""
        if self.simulated_airtime_seconds == 0.0:
            return 0.0
        return self.delivered_payload_bits / self.simulated_airtime_seconds

    @property
    def success_confidence_95(self) -> tuple[float, float]:
        """Return a Wilson 95% interval for frame success percentage."""
        return wilson_interval(self.successful_frames, self.frame_count)

    @property
    def coded_ebn0_db(self) -> float | None:
        """Return energy per coded bit over noise density for this modulation."""
        if self.esn0_db is None:
            return None
        return self.esn0_db - 10.0 * math.log10(bits_per_symbol(self.modulation))


@dataclass(frozen=True, slots=True)
class SweepConfig:
    """Configuration for a repeatable reference-bandwidth SNR sweep."""

    start_snr_db: float = -24.0
    stop_snr_db: float = 10.0
    step_snr_db: float = 2.0
    frames_per_point: int = 200
    seeds: tuple[int, ...] = (2026, 2027, 2028, 2029)
    reference_bandwidth_hz: float = 2_500.0
    symbol_rate: float = 31.25
    frequency_offset_hz: float = 0.0
    impairments: ChannelImpairments = AWGN_IMPAIRMENTS
    interleaver_columns: int | None = None


@dataclass(frozen=True, slots=True)
class RobustnessSweepResult:
    """Completed points and state from one modulation robustness sweep."""

    modulation: str
    config: SweepConfig
    points: tuple[BenchmarkResult, ...]
    cancelled: bool
    elapsed_seconds: float

    def threshold_snr_db(self, target_percent: float) -> float | None:
        """Estimate a bracketed frame-success threshold in reference SNR."""
        return estimate_threshold_snr_db(self.points, target_percent)


def bits_per_symbol(modulation: str) -> int:
    """Return the number of coded bits represented by one modulation symbol."""
    normalized = modulation.upper()
    if normalized == "BPSK":
        return 1
    if normalized == "QPSK":
        return 2
    raise ValueError(f"Unsupported modulation: {modulation}")


def snr_to_esn0_db(
    snr_db: float, reference_bandwidth_hz: float, symbol_rate: float
) -> float:
    """Convert reference-bandwidth SNR to symbol energy over noise density."""
    if reference_bandwidth_hz <= 0.0 or symbol_rate <= 0.0:
        raise ValueError("Reference bandwidth and symbol rate must be positive")
    return snr_db + 10.0 * math.log10(reference_bandwidth_hz / symbol_rate)


def snr_to_coded_ebn0_db(
    snr_db: float,
    reference_bandwidth_hz: float,
    symbol_rate: float,
    modulation: str,
) -> float:
    """Convert reference-bandwidth SNR to coded-bit energy over noise density."""
    esn0_db = snr_to_esn0_db(snr_db, reference_bandwidth_hz, symbol_rate)
    return esn0_db - 10.0 * math.log10(bits_per_symbol(modulation))


def estimate_threshold_snr_db(
    points: tuple[BenchmarkResult, ...], target_percent: float
) -> float | None:
    """Linearly interpolate a success threshold only when points bracket it."""
    if not 0.0 <= target_percent <= 100.0:
        raise ValueError("Target percentage must be between 0 and 100")
    ordered = sorted(points, key=lambda point: point.snr_db)
    for lower, upper in zip(ordered, ordered[1:]):
        lower_rate = lower.success_rate
        upper_rate = upper.success_rate
        if lower_rate <= target_percent <= upper_rate and upper_rate > lower_rate:
            fraction = (target_percent - lower_rate) / (upper_rate - lower_rate)
            return lower.snr_db + fraction * (upper.snr_db - lower.snr_db)
    return None


def _fading_envelope(
    length: int,
    impairments: ChannelImpairments,
    random: np.random.Generator,
) -> NDArray[np.float64]:
    """Create a unit-RMS fading envelope with a seeded random start phase."""
    if length <= 0:
        return np.ones(0, dtype=np.float64)
    indices = np.arange(length, dtype=float)
    start_phase = random.uniform(0.0, 2.0 * math.pi)
    phase = (
        start_phase
        + 2.0
        * math.pi
        * impairments.fading_cycles_per_frame
        * indices
        / length
    )
    envelope = 1.0 + impairments.fading_depth * np.sin(phase)
    envelope /= math.sqrt(float(np.mean(envelope * envelope)))
    return envelope


def _impulse_mask(
    length: int,
    probability: float,
    burst_symbols: int,
    random: np.random.Generator,
) -> NDArray[np.bool_]:
    """Create seeded impulse starts expanded into contiguous symbol bursts."""
    if length < 0 or burst_symbols <= 0:
        raise ValueError("Impulse mask length and burst size are invalid")
    starts = random.random(length) < probability
    mask = starts.copy()
    for offset in range(1, burst_symbols):
        mask[offset:] |= starts[:-offset]
    return mask


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """Return a Wilson 95% confidence interval as percentages."""
    if trials <= 0 or not 0 <= successes <= trials:
        return 0.0, 0.0
    z = 1.959963984540054
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    margin = z * math.sqrt(
        proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials)
    ) / denominator
    return 100.0 * max(0.0, center - margin), 100.0 * min(1.0, center + margin)


class TestingController:
    """Generate deterministic display samples and local codec round trips."""

    def __init__(self, sample_rate: int = 12_000, block_size: int = 1_024) -> None:
        if sample_rate <= 0 or block_size <= 0:
            raise ValueError("Simulation sample rate and block size must be positive")
        self.sample_rate = sample_rate
        self.block_size = block_size
        self._sample_index = 0
        self._random = np.random.default_rng(2026)

    def generate_samples(self) -> tuple[NDArray[np.float32], SimulationDiagnostics]:
        """Generate one repeatable HF-like test block and its display metrics."""
        indices = self._sample_index + np.arange(self.block_size)
        time_values = indices / self.sample_rate
        slow_fade = 0.58 + 0.18 * np.sin(2.0 * math.pi * 0.17 * time_values)
        primary = slow_fade * np.sin(2.0 * math.pi * 1_507.5 * time_values)
        secondary = 0.20 * np.sin(2.0 * math.pi * 1_080.0 * time_values + 0.8)
        interference = 0.10 * np.sin(2.0 * math.pi * 1_930.0 * time_values)
        noise = self._random.normal(0.0, 0.065, self.block_size)
        samples = (primary + secondary + interference + noise).astype(np.float32)
        self._sample_index += self.block_size

        elapsed = self._sample_index / self.sample_rate
        diagnostics = SimulationDiagnostics(
            synchronized=True,
            snr_db=11.5 + 2.5 * math.sin(elapsed * 0.45),
            frequency_offset_hz=7.5,
            timing_offset=0.12 + 0.03 * math.sin(elapsed * 0.3),
            crc_status="WAITING",
            fec_status="IDLE",
        )
        return samples, diagnostics

    def local_round_trip(self, text: str, modulation: str) -> LocalTestResult:
        """Exercise the Aurora codec locally without generating RF or audio."""
        message = text.strip()
        if not message:
            raise ValueError("Enter a message for the local test")

        transmission = encode_payload(message.encode("utf-8"), modulation=modulation)
        symbols = np.asarray(transmission.symbols, dtype=np.complex128)
        noise = self._random.normal(0.0, 0.035, len(symbols)) + 1j * self._random.normal(
            0.0, 0.035, len(symbols)
        )
        received = tuple(symbols + noise)
        decoded = decode_soft_symbols(
            received,
            transmission.modulation,
            noise_variance=0.035**2,
        )
        diagnostics = SimulationDiagnostics(
            synchronized=True,
            snr_db=17.0,
            frequency_offset_hz=0.0,
            timing_offset=0.0,
            crc_status="PASS",
            fec_status="SOFT DECODE PASS",
        )
        return LocalTestResult(
            transmitted_text=message,
            received_text=decoded.payload.decode("utf-8"),
            modulation=transmission.modulation.upper(),
            diagnostics=diagnostics,
        )

    def run_benchmark(
        self,
        text: str,
        modulation: str,
        *,
        snr_db: float,
        frequency_offset_hz: float,
        frame_count: int,
        preset_name: str = "Custom",
        seed: int = 2026,
        symbol_rate: float = 3_000.0,
        reference_bandwidth_hz: float | None = None,
        should_continue: Callable[[], bool] | None = None,
        impairments: ChannelImpairments = AWGN_IMPAIRMENTS,
        interleaver_columns: int | None = None,
    ) -> BenchmarkResult:
        """Run repeatable impaired symbol-domain codec frames."""
        message = text.strip()
        if not message:
            raise ValueError("Enter a message for the channel test")
        if frame_count <= 0 or frame_count > 1_000:
            raise ValueError("Frame count must be between 1 and 1000")
        if symbol_rate <= 0.0:
            raise ValueError("Symbol rate must be positive")
        if reference_bandwidth_hz is not None and reference_bandwidth_hz <= 0.0:
            raise ValueError("Reference bandwidth must be positive")
        if interleaver_columns is not None and interleaver_columns <= 0:
            raise ValueError("Interleaver columns must be positive")

        random = np.random.default_rng(seed)
        successful_frames = 0
        channel_bit_errors = 0
        corrected_bit_errors = 0
        total_coded_bits = 0
        delivered_payload_bits = 0
        simulated_airtime_seconds = 0.0
        completed_frames = 0
        cancelled = False
        esn0_db = (
            snr_to_esn0_db(snr_db, reference_bandwidth_hz, symbol_rate)
            if reference_bandwidth_hz is not None
            else snr_db
        )
        started = time.perf_counter()
        for frame_index in range(frame_count):
            if should_continue is not None and not should_continue():
                cancelled = True
                break
            payload = f"{message} [{frame_index + 1}/{frame_count}]".encode("utf-8")
            transmission = encode_payload(
                payload,
                modulation=modulation,
                interleaver_columns=interleaver_columns,
            )
            original = np.asarray(transmission.symbols, dtype=np.complex128)
            impaired, noise_variance = self._impair_symbols(
                original,
                esn0_db,
                frequency_offset_hz,
                symbol_rate,
                random,
                impairments,
            )
            source_bits = demap_symbols(original, transmission.modulation)
            received_bits = demap_symbols(impaired, transmission.modulation)
            completed_frames += 1
            total_coded_bits += len(source_bits)
            simulated_airtime_seconds += len(original) / symbol_rate
            frame_errors = sum(
                source != received
                for source, received in zip(source_bits, received_bits, strict=True)
            )
            channel_bit_errors += frame_errors
            try:
                decoded = decode_soft_symbols(
                    tuple(impaired),
                    transmission.modulation,
                    noise_variance=noise_variance,
                    interleaver_columns=transmission.interleaver_columns,
                )
                if decoded.payload == payload:
                    successful_frames += 1
                    corrected_bit_errors += frame_errors
                    delivered_payload_bits += len(payload) * 8
            except (UnicodeDecodeError, ValueError):
                continue

        return BenchmarkResult(
            preset_name=preset_name,
            modulation=modulation.upper(),
            snr_db=snr_db,
            frequency_offset_hz=frequency_offset_hz,
            frame_count=completed_frames,
            successful_frames=successful_frames,
            channel_bit_errors=channel_bit_errors,
            corrected_bit_errors=corrected_bit_errors,
            elapsed_seconds=time.perf_counter() - started,
            total_coded_bits=total_coded_bits,
            delivered_payload_bits=delivered_payload_bits,
            simulated_airtime_seconds=simulated_airtime_seconds,
            reference_bandwidth_hz=reference_bandwidth_hz,
            symbol_rate=symbol_rate,
            esn0_db=esn0_db,
            cancelled=cancelled,
            impairments=impairments,
            interleaver_columns=interleaver_columns,
        )

    def run_snr_sweep(
        self,
        text: str,
        modulation: str,
        config: SweepConfig,
        *,
        should_continue: Callable[[], bool] | None = None,
        on_point: Callable[[BenchmarkResult, int, int], None] | None = None,
    ) -> RobustnessSweepResult:
        """Run a cancellable multi-seed reference-bandwidth SNR sweep."""
        if config.step_snr_db <= 0.0 or config.start_snr_db > config.stop_snr_db:
            raise ValueError("Sweep SNR range and step are invalid")
        if config.frames_per_point <= 0:
            raise ValueError("Sweep frames per point must be positive")
        if not config.seeds:
            raise ValueError("Sweep requires at least one random seed")

        point_count = int(
            math.floor(
                (config.stop_snr_db - config.start_snr_db) / config.step_snr_db
                + 1e-9
            )
        ) + 1
        snr_values = [
            config.start_snr_db + index * config.step_snr_db
            for index in range(point_count)
        ]
        points: list[BenchmarkResult] = []
        cancelled = False
        started = time.perf_counter()
        for point_index, snr_db in enumerate(snr_values, start=1):
            if should_continue is not None and not should_continue():
                cancelled = True
                break
            seed_results: list[BenchmarkResult] = []
            base_frames, remainder = divmod(config.frames_per_point, len(config.seeds))
            for seed_index, seed in enumerate(config.seeds):
                frames = base_frames + (1 if seed_index < remainder else 0)
                if frames == 0:
                    continue
                result = self.run_benchmark(
                    text,
                    modulation,
                    snr_db=snr_db,
                    frequency_offset_hz=config.frequency_offset_hz,
                    frame_count=frames,
                    preset_name=f"Sweep {snr_db:+.1f} dB",
                    seed=seed,
                    symbol_rate=config.symbol_rate,
                    reference_bandwidth_hz=config.reference_bandwidth_hz,
                    should_continue=should_continue,
                    impairments=config.impairments,
                    interleaver_columns=config.interleaver_columns,
                )
                seed_results.append(result)
                if result.cancelled:
                    cancelled = True
                    break
            if not seed_results:
                break
            point = self._combine_sweep_point(seed_results, snr_db, config)
            points.append(point)
            if on_point is not None:
                on_point(point, point_index, point_count)
            if cancelled:
                break

        return RobustnessSweepResult(
            modulation=modulation.upper(),
            config=config,
            points=tuple(points),
            cancelled=cancelled,
            elapsed_seconds=time.perf_counter() - started,
        )

    @staticmethod
    def _combine_sweep_point(
        results: list[BenchmarkResult], snr_db: float, config: SweepConfig
    ) -> BenchmarkResult:
        return BenchmarkResult(
            preset_name=f"Sweep {snr_db:+.1f} dB",
            modulation=results[0].modulation,
            snr_db=snr_db,
            frequency_offset_hz=config.frequency_offset_hz,
            frame_count=sum(result.frame_count for result in results),
            successful_frames=sum(result.successful_frames for result in results),
            channel_bit_errors=sum(result.channel_bit_errors for result in results),
            corrected_bit_errors=sum(result.corrected_bit_errors for result in results),
            elapsed_seconds=sum(result.elapsed_seconds for result in results),
            total_coded_bits=sum(result.total_coded_bits for result in results),
            delivered_payload_bits=sum(result.delivered_payload_bits for result in results),
            simulated_airtime_seconds=sum(
                result.simulated_airtime_seconds for result in results
            ),
            reference_bandwidth_hz=config.reference_bandwidth_hz,
            symbol_rate=config.symbol_rate,
            esn0_db=snr_to_esn0_db(
                snr_db, config.reference_bandwidth_hz, config.symbol_rate
            ),
            cancelled=any(result.cancelled for result in results),
            impairments=config.impairments,
            interleaver_columns=config.interleaver_columns,
        )

    @staticmethod
    def _impair_symbols(
        symbols: NDArray[np.complex128],
        snr_db: float,
        frequency_offset_hz: float,
        symbol_rate: float,
        random: np.random.Generator,
        impairments: ChannelImpairments = AWGN_IMPAIRMENTS,
    ) -> tuple[NDArray[np.complex128], float]:
        working = symbols.copy()
        indices = np.arange(len(working), dtype=float)

        if impairments.timing_offset_symbols > 0.0 and len(working) > 1:
            delayed = np.empty_like(working)
            delayed[0] = 0.0
            delayed[1:] = working[:-1]
            fraction = impairments.timing_offset_symbols
            working = (1.0 - fraction) * working + fraction * delayed

        if impairments.multipath_gain > 0.0:
            delay = impairments.multipath_delay_symbols
            if delay <= 0:
                raise ValueError("Active multipath requires a positive delay")
            echo = np.zeros_like(working)
            if delay < len(working):
                echo[delay:] = working[:-delay]
            gain = impairments.multipath_gain
            working = (working + gain * echo) / math.sqrt(1.0 + gain * gain)

        if impairments.fading_depth > 0.0 and len(working) > 0:
            working *= _fading_envelope(len(working), impairments, random)

        if impairments.phase_drift_radians != 0.0 and len(working) > 1:
            drift_phase = (
                impairments.phase_drift_radians
                * indices
                * indices
                / ((len(working) - 1) ** 2)
            )
            working *= np.exp(1j * drift_phase)

        snr_linear = 10.0 ** (snr_db / 10.0)
        noise_variance = 1.0 / snr_linear
        sigma = math.sqrt(noise_variance / 2.0)
        noise = random.normal(0.0, sigma, len(symbols)) + 1j * random.normal(
            0.0, sigma, len(symbols)
        )
        rotation = np.exp(
            2j * math.pi * frequency_offset_hz * indices / symbol_rate
        )
        impaired = working * rotation + noise
        if impairments.impulse_probability > 0.0:
            impulse_mask = _impulse_mask(
                len(working),
                impairments.impulse_probability,
                impairments.impulse_burst_symbols,
                random,
            )
            impulse_count = int(np.count_nonzero(impulse_mask))
            if impulse_count:
                impulses = random.normal(0.0, sigma, impulse_count) + 1j * random.normal(
                    0.0, sigma, impulse_count
                )
                impaired[impulse_mask] += impairments.impulse_scale * impulses
        return impaired, noise_variance
