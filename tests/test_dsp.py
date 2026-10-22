"""DSP 层测试：计权、时间计权、电平换算、频谱。

这些是全部指标的算术基础，错了后面所有界面和报告都白搭。
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_core.dsp.framing import block_frames, mean_square, remove_dc
from audio_core.dsp.level import (
    DB_FLOOR,
    calibration_offset,
    dbfs_to_spl,
    mean_square_to_db,
)
from audio_core.dsp.spectrum import dominant_frequency, spectrum_db
from audio_core.dsp.time_weight import TimeWeighter, fast_weighter
from audio_core.dsp.weighting import WeightingFilter, a_weight_db, c_weight_db

FS = 48000


# ------------------------------------------------------------------ 计权曲线


@pytest.mark.parametrize(
    ("freq", "expected", "tolerance"),
    [(1000.0, 0.0, 0.1), (100.0, -19.1, 0.5), (20.0, -50.4, 1.0), (10000.0, -2.5, 0.5)],
)
def test_a_weight_analytic_matches_standard(freq, expected, tolerance) -> None:
    assert float(a_weight_db(freq)) == pytest.approx(expected, abs=tolerance)


def test_c_weight_at_1khz_is_zero() -> None:
    assert float(c_weight_db(1000.0)) == pytest.approx(0.0, abs=0.1)


def test_weighting_filter_is_normalised_at_1khz() -> None:
    for kind in ("A", "C"):
        assert WeightingFilter(kind, FS).gain_at(1000.0) == pytest.approx(1.0, rel=1e-6)


def test_weighting_filter_tracks_analytic_curve() -> None:
    filt = WeightingFilter("A", FS)
    for freq in (100.0, 500.0, 2000.0):
        measured = 20 * np.log10(filt.gain_at(freq))
        assert measured == pytest.approx(float(a_weight_db(freq)), abs=0.5)


@pytest.mark.parametrize(("freq", "expected"), [(1000.0, 0.0), (100.0, -19.1)])
def test_weighting_filter_gain_on_sine(freq, expected) -> None:
    """正弦实测增益应与解析曲线一致——这是计权实现正确性的直接证据。"""
    filt = WeightingFilter("A", FS)
    t = np.arange(int(2.0 * FS)) / FS
    x = 0.5 * np.sin(2 * np.pi * freq * t)
    y = filt.process(x)
    skip = int(0.5 * FS)
    gain_db = 20 * np.log10(np.std(y[skip:]) / np.std(x[skip:]))
    assert gain_db == pytest.approx(expected, abs=0.3)


# ------------------------------------------------------------------ 时间计权


def test_fast_time_weighting_reaches_63_percent_at_tau() -> None:
    weighter = fast_weighter(0.01)
    weighter.update(0.0)
    for _ in range(13):  # 130 ms ≈ 1 tau
        value = weighter.update(1.0)
    assert value == pytest.approx(1 - np.exp(-1), abs=0.04)


def test_time_weighter_handles_zero_input() -> None:
    weighter = TimeWeighter(0.125, 0.01)
    assert weighter.update(0.0) == 0.0


def test_time_weighter_rejects_bad_tau() -> None:
    with pytest.raises(ValueError):
        TimeWeighter(0.0, 0.01)


# ------------------------------------------------------------------ 电平换算


def test_full_scale_sine_is_minus_3dbfs() -> None:
    t = np.arange(FS) / FS
    sine = np.sin(2 * np.pi * 1000 * t)
    assert mean_square_to_db(mean_square(sine)) == pytest.approx(-3.0103, abs=0.01)


def test_silence_hits_floor_without_nan() -> None:
    level = mean_square_to_db(0.0)
    assert level == DB_FLOOR
    assert np.isfinite(level)


def test_calibration_roundtrip() -> None:
    offset = calibration_offset(94.0, -30.0)
    assert offset == pytest.approx(124.0)
    assert dbfs_to_spl(-30.0, offset) == pytest.approx(94.0)


def test_uncalibrated_returns_none() -> None:
    assert dbfs_to_spl(-30.0, None) is None


def test_remove_dc_kills_offset() -> None:
    block = np.ones(480, dtype=np.float32) * 0.3
    assert abs(float(np.mean(remove_dc(block)))) < 1e-9


# ------------------------------------------------------------------ 频谱


def test_spectrum_finds_tone() -> None:
    n = 16384
    t = np.arange(n) / FS
    block = np.sin(2 * np.pi * 1000 * t)
    assert dominant_frequency(block, FS, n_fft=n) == pytest.approx(1000.0, abs=3.0)


def test_spectrum_peak_is_near_zero_for_full_scale_tone() -> None:
    t = np.arange(2048) / FS
    freq = 24 * FS / 2048  # 精确落在频点上，避免扇贝损失
    block = np.sin(2 * np.pi * freq * t)
    _, db = spectrum_db(block, FS)
    assert float(np.max(db)) == pytest.approx(0.0, abs=0.1)


def test_spectrum_handles_empty_input() -> None:
    freqs, db = spectrum_db(np.empty(0), FS)
    assert freqs.size == db.size > 0
    assert np.all(np.isfinite(db))


def test_block_frames_has_floor() -> None:
    assert block_frames(48000) == 480
    assert block_frames(1000) == 256
