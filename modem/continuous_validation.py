"""Reproducible false-decode validation for Aurora continuous reception."""

from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
import json
import math
import os
import time

import numpy as np

from audio.buffer import AudioBuffer
from audio.continuous_receiver import (
    ContinuousAudioReceiver,
    ContinuousReceiverConfig,
)
from dsp.core import encode_payload
from modem.mode_definition import AURORA_ROBUST_MODE


@dataclass(frozen=True, slots=True)
class ContinuousNoiseValidationConfig:
    """Select one deterministic, optionally parallel noise-only campaign."""

    trials: int = 1_000
    start_trial: int = 0
    batch_size: int | None = None
    seed_base: int = 2_707_260
    noise_standard_deviation: float = 0.15
    payload: bytes = b"A085"
    workers: int = 1

    def __post_init__(self) -> None:
        if self.trials < 0 or self.start_trial < 0:
            raise ValueError("Validation trial counts must not be negative")
        if self.batch_size is not None and self.batch_size <= 0:
            raise ValueError("Batch size must be positive")
        if self.noise_standard_deviation <= 0.0:
            raise ValueError("Noise standard deviation must be positive")
        if not self.payload:
            raise ValueError("Validation payload must not be empty")
        if self.workers <= 0:
            raise ValueError("Worker count must be positive")


@dataclass(frozen=True, slots=True)
class ContinuousNoiseValidationResult:
    """Summarize one deterministic continuous-receiver noise campaign."""

    noise_trials: int
    false_decodes: int
    start_trial: int
    next_trial: int
    elapsed_seconds: float
    false_decode_confidence_95: tuple[float, float]
    worker_count: int
    measurement_domain: str = "continuous_receiver_noise"
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


def _trial_range(config: ContinuousNoiseValidationConfig) -> range:
    count = config.trials
    if config.batch_size is not None:
        count = min(count, config.batch_size)
    return range(config.start_trial, config.start_trial + count)


def _run_noise_chunk(
    arguments: tuple[ContinuousNoiseValidationConfig, tuple[int, ...]],
) -> tuple[int, int]:
    config, trial_indices = arguments
    transmission = encode_payload(
        config.payload,
        modulation=AURORA_ROBUST_MODE.modulation,
        interleaver_columns=AURORA_ROBUST_MODE.interleaver_columns,
    )
    receiver_config = ContinuousReceiverConfig(
        len(transmission.symbols),
        search_margin_seconds=0.1,
    )
    false_decodes = 0
    for trial_index in trial_indices:
        random = np.random.default_rng(config.seed_base + trial_index)
        samples = random.normal(
            0.0,
            config.noise_standard_deviation,
            receiver_config.maximum_buffer_samples,
        ).astype(np.float32)
        receiver = ContinuousAudioReceiver(receiver_config)
        events = receiver.feed(
            AudioBuffer(samples, AURORA_ROBUST_MODE.audio_sample_rate)
        )
        false_decodes += len(events)
    return len(trial_indices), false_decodes


def run_continuous_noise_validation(
    config: ContinuousNoiseValidationConfig = ContinuousNoiseValidationConfig(),
) -> ContinuousNoiseValidationResult:
    """Run a deterministic matched-path noise campaign without audio hardware."""
    trial_indices = tuple(_trial_range(config))
    worker_count = min(config.workers, max(len(trial_indices), 1))
    chunks = tuple(
        tuple(trial_indices[offset::worker_count])
        for offset in range(worker_count)
    )
    started = time.perf_counter()
    if worker_count == 1:
        outcomes = (_run_noise_chunk((config, chunks[0])),)
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            outcomes = tuple(
                executor.map(
                    _run_noise_chunk,
                    ((config, chunk) for chunk in chunks),
                )
            )
    completed = sum(outcome[0] for outcome in outcomes)
    false_decodes = sum(outcome[1] for outcome in outcomes)
    return ContinuousNoiseValidationResult(
        completed,
        false_decodes,
        config.start_trial,
        config.start_trial + completed,
        time.perf_counter() - started,
        _wilson(false_decodes, completed),
        worker_count,
    )


def main() -> int:
    """Run the command-line continuous-receiver noise campaign."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=1_000)
    parser.add_argument("--start-trial", type=int, default=0)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument(
        "--workers",
        type=int,
        default=min(os.cpu_count() or 1, 12),
    )
    arguments = parser.parse_args()
    config = ContinuousNoiseValidationConfig(
        trials=arguments.trials,
        start_trial=arguments.start_trial,
        batch_size=arguments.batch_size,
        workers=arguments.workers,
    )
    print(json.dumps(asdict(run_continuous_noise_validation(config)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
