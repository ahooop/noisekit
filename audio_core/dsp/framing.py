"""分帧与基础时域运算。"""

from __future__ import annotations

import numpy as np

MIN_BLOCK_FRAMES = 256


def block_frames(sample_rate: int, seconds: float = 0.01) -> int:
    """指标块长：默认 10 ms，且不小于 256 样本（否则低压滤波器的瞬态占比过大）。"""
    return max(MIN_BLOCK_FRAMES, int(round(seconds * sample_rate)))


def remove_dc(block: np.ndarray) -> np.ndarray:
    """去直流。麦克风前置放大常有几十 mV 偏置，不去会污染 Leq。"""
    data = np.asarray(block, dtype=np.float64)
    return data - float(np.mean(data)) if data.size else data


def mean_square(block: np.ndarray) -> float:
    """均方值。空块返回 0.0。"""
    data = np.asarray(block, dtype=np.float64)
    if data.size == 0:
        return 0.0
    return float(np.mean(data * data))


def peak_amplitude(block: np.ndarray) -> float:
    data = np.asarray(block, dtype=np.float64)
    return float(np.max(np.abs(data))) if data.size else 0.0
