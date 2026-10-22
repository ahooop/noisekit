"""SoundLevelMeter 的集成测试：用合成信号驱动完整链路。"""

from __future__ import annotations

import numpy as np
import pytest

from audio_core.capture.synthetic import SyntheticSource
from audio_core.dsp.level import DB_FLOOR
from audio_core.metrics.meter import SoundLevelMeter

FS = 48000


def drive(meter: SoundLevelMeter, source: SyntheticSource, skip_first: float = 0.0):
    """喂完整段信号，返回 (所有帧, 跳过起始后的帧)。"""
    frames = []
    consumed = 0
    for block in source.blocks():
        frame = meter.process(block, consumed / FS)
        frames.append(frame)
        consumed += block.size
    return frames, [f for f in frames if f.ts >= skip_first]


def test_full_scale_sine_level() -> None:
    meter = SoundLevelMeter(FS)
    source = SyntheticSource(sample_rate=FS, freq=1000.0, amplitude=1.0, duration=2.0)
    _, frames = drive(meter, source, skip_first=0.5)

    last = frames[-1]
    assert last.dbfs == pytest.approx(-3.01, abs=0.05)
    assert last.db_a == pytest.approx(-3.01, abs=0.1)
    assert last.db_c == pytest.approx(-3.01, abs=0.1)


def test_lequivalent_converges_to_stationary_level() -> None:
    meter = SoundLevelMeter(FS)
    source = SyntheticSource(freq=1000.0, amplitude=0.5, duration=3.0)
    _, frames = drive(meter, source, skip_first=0.5)

    average = float(np.mean([f.db_a for f in frames[-50:]]))
    assert frames[-1].leq_10s == pytest.approx(average, abs=0.15)
    assert frames[-1].leq_session == pytest.approx(average, abs=0.15)


def test_silence_never_produces_nan() -> None:
    meter = SoundLevelMeter(FS)
    source = SyntheticSource(amplitude=0.0, duration=0.5)
    _, frames = drive(meter, source)

    for frame in frames:
        values = [frame.dbfs, frame.db_a, frame.db_c, frame.laf, frame.las]
        assert all(np.isfinite(v) for v in values)
        assert frame.dbfs == DB_FLOOR
        assert frame.lcpeak == DB_FLOOR


def test_timestamps_are_monotonic() -> None:
    meter = SoundLevelMeter(FS)
    source = SyntheticSource(amplitude=0.1, duration=1.0)
    frames, _ = drive(meter, source)
    stamps = [f.ts for f in frames]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


def test_calibration_shifts_spl_only() -> None:
    meter = SoundLevelMeter(FS, calibration_offset=124.0)
    source = SyntheticSource(freq=1000.0, amplitude=1.0, duration=1.0)
    _, frames = drive(meter, source, skip_first=0.5)

    last = frames[-1]
    assert last.spl_a == pytest.approx(last.db_a + 124.0, abs=1e-6)
    assert last.calibrated


def test_uncalibrated_frame_has_no_absolute_level() -> None:
    meter = SoundLevelMeter(FS)
    source = SyntheticSource(amplitude=0.5, duration=0.5)
    _, frames = drive(meter, source)
    assert frames[-1].spl_a is None
    assert not frames[-1].calibrated
    assert frames[-1].display_level() == frames[-1].db_a


def test_peak_metrics_are_consistent() -> None:
    meter = SoundLevelMeter(FS)
    source = SyntheticSource(freq=1000.0, amplitude=1.0, duration=1.0)
    _, frames = drive(meter, source, skip_first=0.3)

    last = frames[-1]
    assert last.lafmax >= last.db_a - 0.2
    assert last.lcpeak >= last.db_c - 0.2


def test_empty_block_is_rejected() -> None:
    meter = SoundLevelMeter(FS)
    with pytest.raises(ValueError):
        meter.process(np.empty(0), 0.0)


def test_reset_clears_state() -> None:
    meter = SoundLevelMeter(FS)
    for block in SyntheticSource(amplitude=1.0, duration=0.2).blocks():
        meter.process(block, 0.0)
    meter.reset()
    assert meter.lafmax == DB_FLOOR
