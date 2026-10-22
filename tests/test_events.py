"""告警状态机与留证录音的测试。"""

from __future__ import annotations

import numpy as np
import pytest

from audio_core.events.detector import State, ThresholdDetector
from audio_core.events.recorder import EventRecorder

FS = 48000


def feed(detector: ThresholdDetector, levels: list[float], start: float = 0.0, step: float = 0.1):
    events = []
    for index, level in enumerate(levels):
        events.extend(detector.update(level, start + index * step))
    return events


# ------------------------------------------------------------------ 状态机


def test_below_threshold_never_triggers() -> None:
    detector = ThresholdDetector(threshold=65.0, trigger_seconds=3.0)
    assert feed(detector, [60.0] * 100) == []
    assert detector.state is State.IDLE


def test_must_exceed_for_trigger_duration() -> None:
    detector = ThresholdDetector(threshold=65.0, trigger_seconds=3.0, post_roll_seconds=5.0)
    # 只超过 2.9 秒，不该触发
    assert feed(detector, [70.0] * 29) == []

    detector = ThresholdDetector(threshold=65.0, trigger_seconds=3.0, post_roll_seconds=5.0)
    events = feed(detector, [70.0] * 31)
    assert len(events) == 1
    assert events[0].kind == "start"
    assert events[0].event.started_at == pytest.approx(0.0)


def test_short_spike_resets_the_clock() -> None:
    """响一下不算，中间掉下去就得重新计时。"""
    detector = ThresholdDetector(threshold=65.0, trigger_seconds=3.0)
    assert feed(detector, [70.0] * 20) == []
    feed(detector, [60.0], start=2.0)
    assert feed(detector, [70.0] * 20, start=2.1) == []


def test_event_ends_after_post_roll() -> None:
    detector = ThresholdDetector(threshold=65.0, trigger_seconds=3.0, post_roll_seconds=5.0)
    events = feed(detector, [70.0] * 31)  # 触发于 t=3.0
    assert len(events) == 1

    # 掉到阈值以下，但要等满 5 秒才结束
    quiet = feed(detector, [60.0] * 49, start=3.1)
    assert quiet == []
    ended = feed(detector, [60.0] * 2, start=8.0)
    assert len(ended) == 1
    assert ended[0].kind == "end"
    assert ended[0].event.ended_at == pytest.approx(3.0)


def test_long_noise_produces_exactly_one_event() -> None:
    detector = ThresholdDetector(threshold=65.0, trigger_seconds=3.0)
    events = feed(detector, [70.0] * 300)
    assert len(events) == 1
    assert events[0].kind == "start"


def test_peak_is_tracked_during_event() -> None:
    detector = ThresholdDetector(threshold=65.0, trigger_seconds=1.0)
    # 前 3 个样本冲到 90，后面回落到 70；触发发生在 t=1.0
    events = feed(detector, [70.0, 80.0, 90.0] + [70.0] * 12)
    assert len(events) == 1
    assert events[0].event.peak == pytest.approx(90.0)


def test_cooldown_suppresses_new_event() -> None:
    detector = ThresholdDetector(
        threshold=65.0, trigger_seconds=1.0, post_roll_seconds=1.0, cooldown_seconds=10.0
    )
    started = feed(detector, [70.0] * 11)
    assert len(started) == 1
    ended = feed(detector, [60.0] * 11, start=1.1)
    assert len(ended) == 1
    # 冷却期内再吵也不触发
    assert feed(detector, [80.0] * 30, start=2.3) == []


def test_force_end_closes_open_event() -> None:
    detector = ThresholdDetector(threshold=65.0, trigger_seconds=1.0)
    feed(detector, [70.0] * 20)
    notification = detector.force_end(2.0)
    assert notification is not None
    assert notification.event.ended_at is not None
    assert detector.state is State.IDLE


def test_negative_durations_rejected() -> None:
    with pytest.raises(ValueError):
        ThresholdDetector(trigger_seconds=-1)


# ------------------------------------------------------------------ 录音


def _sine(seconds: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(int(seconds * FS)) / FS
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def test_recorder_keeps_pre_roll(tmp_path) -> None:
    recorder = EventRecorder(FS, tmp_path, pre_roll_seconds=1.0)
    signal = _sine(1.5)
    for start in range(0, signal.size, 480):
        recorder.push(signal[start : start + 480])

    recorder.begin()
    for start in range(0, _sine(1.0).size, 480):
        recorder.push(signal[start : start + 480])
    path = recorder.finish()

    assert path is not None and path.exists()
    from scipy.io import wavfile

    rate, data = wavfile.read(path)
    assert rate == FS
    # 1 秒前置 + 1 秒实时 ≈ 2 秒
    assert data.size / FS == pytest.approx(2.0, abs=0.05)
    assert np.max(np.abs(data.astype(np.float32) / 32768.0)) > 0.1


def test_recorder_is_idempotent_and_clean(tmp_path) -> None:
    recorder = EventRecorder(FS, tmp_path, pre_roll_seconds=0.5)
    recorder.push(_sine(0.2))
    assert recorder.finish() is None
    first = recorder.begin()
    second = recorder.begin()
    assert first == second
    recorder.finish()
    assert not recorder.recording


def test_recorder_clips_out_of_range_samples(tmp_path) -> None:
    recorder = EventRecorder(FS, tmp_path, pre_roll_seconds=0.0)
    recorder.begin()
    loud = np.array([2.0, -2.0, 0.0, 0.5], dtype=np.float32)
    recorder.push(loud)
    path = recorder.finish()

    from scipy.io import wavfile

    _, data = wavfile.read(path)
    assert data.max() <= 32767
    assert data.min() >= -32768
