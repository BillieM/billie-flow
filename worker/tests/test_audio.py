from __future__ import annotations

import struct
import sys
import types
import wave

import numpy as np
import pytest

from billie_flow_worker.audio import InvalidAudioError, read_pcm_wav, validate_pcm_wav
from billie_flow_worker.runtime import MLXRuntime


def write_samples(path, samples, *, rate=16_000, channels=1, width=2):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        if width == 2:
            output.writeframes(struct.pack(f"<{len(samples)}h", *samples))
        else:
            output.writeframes(bytes(samples))
    return path


def test_pcm_decode_normalises_to_flat_float32_without_ffmpeg(tmp_path):
    audio = write_samples(tmp_path / "levels.wav", [-32768, -16384, 0, 16384, 32767])
    samples = read_pcm_wav(str(audio))
    assert samples.dtype == np.float32
    assert samples.shape == (5,)
    np.testing.assert_allclose(
        samples,
        np.array([-1.0, -0.5, 0.0, 0.5, 32767 / 32768], dtype=np.float32),
    )


@pytest.mark.parametrize(
    ("rate", "channels", "width"),
    [(8_000, 1, 2), (16_000, 2, 2), (16_000, 1, 1)],
)
def test_pcm_decode_rejects_every_unsupported_format(tmp_path, rate, channels, width):
    audio = write_samples(
        tmp_path / f"invalid-{rate}-{channels}-{width}.wav",
        [0, 0] if width == 2 else [0, 0, 0, 0],
        rate=rate,
        channels=channels,
        width=width,
    )
    assert validate_pcm_wav(str(audio)) is False
    with pytest.raises(InvalidAudioError):
        read_pcm_wav(str(audio))


def test_mlx_runtime_passes_pcm_array_not_path_to_whisper(tmp_path, monkeypatch):
    audio = write_samples(tmp_path / "recording.wav", [-32768, 0, 32767])
    captured = {}

    def fake_transcribe(value, **kwargs):
        captured["value"] = value
        captured["kwargs"] = kwargs
        return {"text": "hello"}

    monkeypatch.setitem(sys.modules, "mlx_whisper", types.SimpleNamespace(transcribe=fake_transcribe))
    runtime = MLXRuntime()
    runtime.asr_loaded = True
    assert runtime.transcribe(str(audio)) == "hello"
    assert isinstance(captured["value"], np.ndarray)
    assert captured["value"].dtype == np.float32
    assert captured["value"].shape == (3,)
    assert captured["kwargs"]["language"] == "en"
    assert str(audio) not in repr(captured["value"])
