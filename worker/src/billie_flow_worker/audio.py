"""Strict WAV decoding without an ffmpeg or subprocess dependency."""

from __future__ import annotations

import os
import wave


class InvalidAudioError(ValueError):
    pass


def validate_pcm_wav(path: str) -> bool:
    try:
        _header(path)
        return True
    except (InvalidAudioError, OSError, EOFError, wave.Error):
        return False


def read_pcm_wav(path: str):
    """Return mono 16 kHz int16 PCM as a normalized NumPy float32 vector."""

    import numpy as np

    with wave.open(path, "rb") as wav:
        frames = _validate_open_wav(wav)
        data = wav.readframes(frames)
    if len(data) != frames * 2:
        raise InvalidAudioError("truncated PCM data")
    samples = np.frombuffer(data, dtype="<i2").astype(np.float32)
    samples /= 32768.0
    return samples


def _header(path: str) -> None:
    if not os.path.isfile(path):
        raise InvalidAudioError("not a file")
    with wave.open(path, "rb") as wav:
        frames = _validate_open_wav(wav)
        if len(wav.readframes(frames)) != frames * 2:
            raise InvalidAudioError("truncated PCM data")


def _validate_open_wav(wav: wave.Wave_read) -> int:
    frames = wav.getnframes()
    if (
        wav.getnchannels() != 1
        or wav.getframerate() != 16_000
        or wav.getsampwidth() != 2
        or wav.getcomptype() != "NONE"
        or frames <= 0
    ):
        raise InvalidAudioError("unsupported WAV format")
    return frames
