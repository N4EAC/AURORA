"""PCM WAV import and export for Aurora."""

from pathlib import Path
import wave

import numpy as np
from numpy.typing import NDArray

from audio.buffer import AudioBuffer


def _decode_pcm(data: bytes, sample_width: int) -> NDArray[np.float32]:
    if sample_width == 1:
        values = np.frombuffer(data, dtype=np.uint8).astype(np.float32)
        return (values - 128.0) / 128.0
    if sample_width == 2:
        values = np.frombuffer(data, dtype="<i2").astype(np.float32)
        return values / 32_768.0
    if sample_width == 3:
        octets = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3)
        values = (
            octets[:, 0].astype(np.int32)
            | (octets[:, 1].astype(np.int32) << 8)
            | (octets[:, 2].astype(np.int32) << 16)
        )
        values = np.where(values & 0x800000, values - 0x1000000, values)
        return values.astype(np.float32) / 8_388_608.0
    if sample_width == 4:
        values = np.frombuffer(data, dtype="<i4").astype(np.float64)
        return (values / 2_147_483_648.0).astype(np.float32)
    raise ValueError(f"Unsupported PCM sample width: {sample_width} bytes")


def read_wav(path: str | Path) -> AudioBuffer:
    """Read an uncompressed PCM WAV file into an audio buffer."""
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getcomptype() != "NONE":
            raise ValueError("Only uncompressed PCM WAV files are supported")
        channel_count = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        frame_count = wav_file.getnframes()
        samples = _decode_pcm(wav_file.readframes(frame_count), sample_width)

    if channel_count > 1:
        samples = samples.reshape(-1, channel_count)
    return AudioBuffer(samples, sample_rate)


def write_wav(path: str | Path, audio: AudioBuffer) -> None:
    """Write an audio buffer as signed 16-bit PCM WAV data."""
    clipped = np.clip(audio.samples, -1.0, 1.0)
    pcm = np.rint(clipped * 32_767.0).astype("<i2")
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(audio.channel_count)
        wav_file.setsampwidth(2)
        wav_file.setframerate(audio.sample_rate)
        wav_file.writeframes(pcm.tobytes())
