"""Offline audio-domain robustness benchmarks for the Aurora modem."""

from collections.abc import Callable
from dataclasses import dataclass, replace
import argparse
import math
import time

import numpy as np

from dsp.audio_channel import AudioChannelConfig, apply_audio_channel
from dsp.core import decode_soft_symbols, encode_payload
from dsp.framing import FrameError
from dsp.waveform import demodulate_audio, modulate_audio, occupied_bandwidth_hz
from modem.mode_definition import AURORA_ROBUST_MODE


EventCallback = Callable[[str, dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class AudioBenchmarkConfig:
    """Configuration for a deterministic audio-domain frame benchmark."""

    frame_count: int = 4
    seed: int = 2026
    frequency_offset_hz: float = 0.0
    leading_silence_samples: int = 137
    channel: AudioChannelConfig = AudioChannelConfig(snr_db=10.0)

    def __post_init__(self) -> None:
        if not 1 <= self.frame_count <= 100:
            raise ValueError("Audio benchmark frame count must be between 1 and 100")
        if self.leading_silence_samples < 0:
            raise ValueError("Leading silence must not be negative")


@dataclass(frozen=True, slots=True)
class AudioBenchmarkResult:
    """Aggregate outcome from an offline audio-domain benchmark."""

    frame_count: int
    synchronized_frames: int
    successful_frames: int
    elapsed_seconds: float
    mean_sync_metric: float | None
    mean_frequency_offset_hz: float | None
    occupied_bandwidth_hz: float
    cancelled: bool
    measurement_domain: str = "audio_sim"

    @property
    def success_rate(self) -> float:
        """Return successfully decoded frames as a percentage."""
        return 0.0 if self.frame_count == 0 else 100.0 * self.successful_frames / self.frame_count


@dataclass(frozen=True, slots=True)
class AudioSweepConfig:
    """Small deterministic SNR sweep suitable for offline audio processing."""

    start_snr_db: float = -10.0
    stop_snr_db: float = 10.0
    step_snr_db: float = 5.0
    frames_per_point: int = 4
    seeds: tuple[int, ...] = (2026, 2027)
    benchmark: AudioBenchmarkConfig = AudioBenchmarkConfig()


@dataclass(frozen=True, slots=True)
class AudioSweepResult:
    """Ordered audio-domain benchmark points and cancellation state."""

    points: tuple[tuple[float, AudioBenchmarkResult], ...]
    cancelled: bool
    elapsed_seconds: float
    measurement_domain: str = "audio_sim"


def _emit(callback: EventCallback | None, event: str, **fields: object) -> None:
    if callback is not None:
        callback(event, fields)


def run_audio_benchmark(
    text: str,
    config: AudioBenchmarkConfig = AudioBenchmarkConfig(),
    *,
    should_continue: Callable[[], bool] | None = None,
    event_callback: EventCallback | None = None,
) -> AudioBenchmarkResult:
    """Run framed Aurora data through an impaired real-audio waveform."""
    message = text.strip()
    if not message:
        raise ValueError("Enter a message for the audio benchmark")
    mode = AURORA_ROBUST_MODE
    random = np.random.default_rng(config.seed)
    completed = 0
    synchronized = 0
    successful = 0
    sync_metrics: list[float] = []
    offsets: list[float] = []
    bandwidth = 0.0
    cancelled = False
    started = time.perf_counter()
    _emit(
        event_callback,
        "AUDIO_ROBUSTNESS_START",
        measurement_domain="audio_sim",
        frame_count=config.frame_count,
        seed=config.seed,
        snr_db=config.channel.snr_db,
        reference_bandwidth_hz=config.channel.reference_bandwidth_hz,
        frequency_offset_hz=config.frequency_offset_hz,
    )
    for frame_index in range(config.frame_count):
        if should_continue is not None and not should_continue():
            cancelled = True
            break
        payload = f"{message} [{frame_index + 1}/{config.frame_count}]".encode()
        transmission = encode_payload(
            payload,
            modulation=mode.modulation,
            interleaver_columns=mode.interleaver_columns,
        )
        clean = modulate_audio(
            transmission.symbols,
            mode,
            leading_silence_samples=config.leading_silence_samples,
            frequency_offset_hz=config.frequency_offset_hz,
        )
        if frame_index == 0:
            bandwidth = occupied_bandwidth_hz(clean)
        impaired = apply_audio_channel(clean, config.channel, random)
        completed += 1
        try:
            recovered = demodulate_audio(impaired, len(transmission.symbols), mode)
            synchronized += 1
            sync_metrics.append(recovered.diagnostics.sync_metric)
            offsets.append(recovered.diagnostics.frequency_offset_hz)
            decoded = decode_soft_symbols(
                tuple(recovered.symbols),
                mode.modulation,
                noise_variance=1.0,
                interleaver_columns=mode.interleaver_columns,
            )
            if decoded.payload == payload:
                successful += 1
        except (FrameError, UnicodeDecodeError, ValueError):
            pass
    result = AudioBenchmarkResult(
        frame_count=completed,
        synchronized_frames=synchronized,
        successful_frames=successful,
        elapsed_seconds=time.perf_counter() - started,
        mean_sync_metric=float(np.mean(sync_metrics)) if sync_metrics else None,
        mean_frequency_offset_hz=float(np.mean(offsets)) if offsets else None,
        occupied_bandwidth_hz=bandwidth,
        cancelled=cancelled,
    )
    _emit(
        event_callback,
        "AUDIO_ROBUSTNESS_END",
        measurement_domain=result.measurement_domain,
        frame_count=result.frame_count,
        synchronized_frames=result.synchronized_frames,
        successful_frames=result.successful_frames,
        success_rate_percent=result.success_rate,
        mean_sync_metric=result.mean_sync_metric,
        mean_frequency_offset_hz=result.mean_frequency_offset_hz,
        occupied_bandwidth_hz=result.occupied_bandwidth_hz,
        cancelled=result.cancelled,
    )
    return result


def run_audio_snr_sweep(
    text: str,
    config: AudioSweepConfig = AudioSweepConfig(),
    *,
    should_continue: Callable[[], bool] | None = None,
    event_callback: EventCallback | None = None,
) -> AudioSweepResult:
    """Run a cancellable, multi-seed offline audio-domain SNR sweep."""
    if config.step_snr_db <= 0.0 or config.start_snr_db > config.stop_snr_db:
        raise ValueError("Audio sweep SNR range and step are invalid")
    if config.frames_per_point <= 0 or not config.seeds:
        raise ValueError("Audio sweep requires frames and random seeds")
    started = time.perf_counter()
    point_count = int(math.floor((config.stop_snr_db - config.start_snr_db) / config.step_snr_db + 1e-9)) + 1
    points: list[tuple[float, AudioBenchmarkResult]] = []
    cancelled = False
    for point_index in range(point_count):
        snr_db = config.start_snr_db + point_index * config.step_snr_db
        seed_results: list[AudioBenchmarkResult] = []
        base_frames, remainder = divmod(config.frames_per_point, len(config.seeds))
        for seed_index, seed in enumerate(config.seeds):
            frames = base_frames + (1 if seed_index < remainder else 0)
            if frames == 0:
                continue
            benchmark = replace(
                config.benchmark,
                frame_count=frames,
                seed=seed,
                channel=replace(config.benchmark.channel, snr_db=snr_db),
            )
            result = run_audio_benchmark(
                text,
                benchmark,
                should_continue=should_continue,
                event_callback=event_callback,
            )
            seed_results.append(result)
            if result.cancelled:
                cancelled = True
                break
        if not seed_results:
            break
        completed = sum(item.frame_count for item in seed_results)
        synced = sum(item.synchronized_frames for item in seed_results)
        passed = sum(item.successful_frames for item in seed_results)
        metrics = [item.mean_sync_metric for item in seed_results if item.mean_sync_metric is not None]
        offsets = [item.mean_frequency_offset_hz for item in seed_results if item.mean_frequency_offset_hz is not None]
        combined = AudioBenchmarkResult(
            completed,
            synced,
            passed,
            sum(item.elapsed_seconds for item in seed_results),
            float(np.mean(metrics)) if metrics else None,
            float(np.mean(offsets)) if offsets else None,
            seed_results[0].occupied_bandwidth_hz,
            cancelled,
        )
        points.append((snr_db, combined))
        _emit(
            event_callback,
            "AUDIO_ROBUSTNESS_POINT",
            measurement_domain="audio_sim",
            snr_db=snr_db,
            frame_count=combined.frame_count,
            successful_frames=combined.successful_frames,
            success_rate_percent=combined.success_rate,
        )
        if cancelled:
            break
    return AudioSweepResult(tuple(points), cancelled, time.perf_counter() - started)


def main() -> int:
    """Run a small logged offline benchmark from the command line."""
    parser = argparse.ArgumentParser(description="Aurora offline audio robustness check")
    parser.add_argument("--message", default="Aurora offline audio check")
    parser.add_argument("--frames", type=int, default=2)
    parser.add_argument("--snr-db", type=float, default=10.0)
    arguments = parser.parse_args()

    from config import SETTINGS
    from util.session_debug_log import SessionDebugLog

    benchmark = AudioBenchmarkConfig(
        frame_count=arguments.frames,
        channel=AudioChannelConfig(snr_db=arguments.snr_db),
    )
    with SessionDebugLog(SETTINGS.log_directory, "0.4.0-dev") as session_log:
        result = run_audio_benchmark(
            arguments.message,
            benchmark,
            event_callback=lambda event, fields: session_log.record(event, **fields),
        )
    print(
        f"audio_sim: {result.successful_frames}/{result.frame_count} frames, "
        f"sync {result.synchronized_frames}/{result.frame_count}, "
        f"{result.elapsed_seconds:.2f} s"
    )
    return 0 if result.successful_frames == result.frame_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
