"""Managed real-time audio streams for Aurora."""

from collections.abc import Callable
import logging
from typing import Any

import numpy as np
from numpy.typing import NDArray
import sounddevice as sd

from audio.buffer import AudioBuffer
from config import AppSettings, SETTINGS


InputConsumer = Callable[[AudioBuffer], None]
OutputProducer = Callable[[int], AudioBuffer | NDArray[np.float32]]
DuplexProcessor = Callable[[AudioBuffer], AudioBuffer | NDArray[np.float32]]


def _report_status(status: Any) -> None:
    if status:
        logging.getLogger("aurora.audio").warning("Audio stream status: %s", status)


def _copy_to_output(
    source: AudioBuffer | NDArray[np.float32], output: NDArray[np.float32]
) -> None:
    samples = source.samples if isinstance(source, AudioBuffer) else source
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim == 1:
        samples = samples[:, np.newaxis]
    if samples.ndim != 2 or samples.shape[1] != output.shape[1]:
        raise ValueError("Stream output channel count does not match its configuration")

    output.fill(0.0)
    frame_count = min(len(samples), len(output))
    output[:frame_count] = np.clip(samples[:frame_count], -1.0, 1.0)


class _ManagedStream:
    """Common lifecycle operations for a sounddevice stream."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    @property
    def active(self) -> bool:
        """Return whether the underlying stream is active."""
        return bool(self._stream.active)

    def start(self) -> None:
        """Start real-time audio processing."""
        self._stream.start()

    def stop(self) -> None:
        """Stop real-time audio processing without closing the stream."""
        self._stream.stop()

    def close(self) -> None:
        """Release the audio stream and its host resources."""
        self._stream.close()

    def __enter__(self) -> "_ManagedStream":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.stop()
        self.close()


class AudioInputStream(_ManagedStream):
    """Real-time stream that supplies captured audio buffers to a consumer."""

    def __init__(
        self,
        consumer: InputConsumer,
        *,
        settings: AppSettings = SETTINGS,
        device: int | str | None = None,
    ) -> None:
        def callback(indata: NDArray[np.float32], frames: int, time: Any, status: Any) -> None:
            del frames, time
            _report_status(status)
            consumer(AudioBuffer(indata.copy(), settings.audio_sample_rate))

        stream = sd.InputStream(
            samplerate=settings.audio_sample_rate,
            blocksize=settings.audio_block_size,
            channels=settings.audio_channels,
            dtype="float32",
            device=device,
            callback=callback,
        )
        super().__init__(stream)


class AudioOutputStream(_ManagedStream):
    """Real-time stream that requests sample frames from a producer."""

    def __init__(
        self,
        producer: OutputProducer,
        *,
        settings: AppSettings = SETTINGS,
        device: int | str | None = None,
    ) -> None:
        def callback(outdata: NDArray[np.float32], frames: int, time: Any, status: Any) -> None:
            del time
            _report_status(status)
            _copy_to_output(producer(frames), outdata)

        stream = sd.OutputStream(
            samplerate=settings.audio_sample_rate,
            blocksize=settings.audio_block_size,
            channels=settings.audio_channels,
            dtype="float32",
            device=device,
            callback=callback,
        )
        super().__init__(stream)


class AudioDuplexStream(_ManagedStream):
    """Real-time full-duplex stream driven by an audio processor callback."""

    def __init__(
        self,
        processor: DuplexProcessor,
        *,
        settings: AppSettings = SETTINGS,
        device: int | str | tuple[int | str, int | str] | None = None,
    ) -> None:
        def callback(
            indata: NDArray[np.float32],
            outdata: NDArray[np.float32],
            frames: int,
            time: Any,
            status: Any,
        ) -> None:
            del frames, time
            _report_status(status)
            input_audio = AudioBuffer(indata.copy(), settings.audio_sample_rate)
            _copy_to_output(processor(input_audio), outdata)

        stream = sd.Stream(
            samplerate=settings.audio_sample_rate,
            blocksize=settings.audio_block_size,
            channels=settings.audio_channels,
            dtype="float32",
            device=device,
            callback=callback,
        )
        super().__init__(stream)
