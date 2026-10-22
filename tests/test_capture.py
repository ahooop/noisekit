"""环形缓冲、合成源、WAV 回放源的测试。不需要麦克风。"""

from __future__ import annotations

import numpy as np
import pytest

from audio_core.capture.ring import RingBuffer
from audio_core.capture.synthetic import SyntheticSource
from audio_core.capture.wav_source import WavFileSource


def test_ring_wraps_around() -> None:
    ring = RingBuffer(capacity=8)
    ring.write(np.arange(8, dtype=np.float32))
    assert ring.available == 8

    first = ring.read(4)
    np.testing.assert_array_equal(first, [0, 1, 2, 3])

    ring.write(np.arange(8, 12, dtype=np.float32))
    np.testing.assert_array_equal(ring.read(8), np.arange(4, 12, dtype=np.float32))
    assert ring.available == 0


def test_ring_overflow_drops_oldest() -> None:
    ring = RingBuffer(capacity=8)
    ring.write(np.arange(8, dtype=np.float32))
    ring.write(np.arange(100, 108, dtype=np.float32))

    assert ring.overflows == 1
    assert ring.dropped_samples == 8
    np.testing.assert_array_equal(ring.read(8), np.arange(100, 108, dtype=np.float32))


def test_ring_oversized_write_keeps_tail() -> None:
    ring = RingBuffer(capacity=4)
    ring.write(np.arange(10, dtype=np.float32))
    np.testing.assert_array_equal(ring.read(4), np.arange(6, 10, dtype=np.float32))


def test_ring_read_more_than_available() -> None:
    ring = RingBuffer(capacity=8)
    ring.write(np.array([1.0, 2.0], dtype=np.float32))
    np.testing.assert_array_equal(ring.read(100), [1.0, 2.0])
    assert ring.read(1).size == 0


def test_ring_rejects_bad_capacity() -> None:
    with pytest.raises(ValueError):
        RingBuffer(capacity=0)


def test_synthetic_duration_is_exact() -> None:
    source = SyntheticSource(sample_rate=48000, duration=0.5)
    blocks = list(source.blocks())
    assert sum(b.size for b in blocks) == 24000
    assert all(b.size <= source.block_frames for b in blocks)


def test_synthetic_sine_amplitude() -> None:
    source = SyntheticSource(sample_rate=48000, freq=1000.0, amplitude=0.5)
    block = next(source.blocks())
    assert np.max(np.abs(block)) <= 0.5 + 1e-6
    assert np.std(block) == pytest.approx(0.5 / np.sqrt(2), rel=0.02)


def test_synthetic_white_noise_is_reproducible() -> None:
    a = next(SyntheticSource(kind="white", seed=7).blocks())
    b = next(SyntheticSource(kind="white", seed=7).blocks())
    np.testing.assert_array_equal(a, b)


def test_wav_source_roundtrip(tmp_path) -> None:
    from scipy.io import wavfile

    fs = 48000
    t = np.arange(int(0.25 * fs)) / fs
    wave = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    path = tmp_path / "tone.wav"
    wavfile.write(path, fs, wave)

    source = WavFileSource(path)
    assert source.sample_rate == fs
    assert source.duration == pytest.approx(0.25, rel=1e-3)
    data = np.concatenate(list(source.blocks()))
    assert data.size == wave.size
    assert np.max(np.abs(data)) <= 0.5 + 1e-3


def test_wav_source_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        WavFileSource(tmp_path / "nope.wav")
