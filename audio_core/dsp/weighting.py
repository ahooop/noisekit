"""A / C 计权（IEC 61672-1）。

两条实现并存，各司其职：

* ``a_weight_db`` / ``c_weight_db``：解析幅频响应，用于绘图、报告与交叉验算；
* ``WeightingFilter``：由模拟原型零极点经双线性变换得到的流式 IIR，
  用于真正算声级——逐样本状态，没有块边界瞬态。

设计文档 §4.3 记录了为什么最终选 IIR 而不是「频域加权」。
"""

from __future__ import annotations

import numpy as np
from scipy import signal

# IEC 61672-1 模拟原型极点（负实轴，单位 rad/s，含重数）。
# 必须为负：双线性变换只把左半平面的极点映到单位圆内，
# 写成正数会让滤波器发散，读数恒为下限。
_A_POLES = -np.array([129.4, 129.4, 676.7, 4636.0, 76655.0, 76655.0])
_C_POLES = -np.array([129.4, 129.4, 76655.0, 76655.0])

_TINY = 1e-30


def a_weight_db(freqs: np.ndarray | float) -> np.ndarray:
    """A 计权幅频响应（dB），1 kHz 处为 0 dB。"""
    f = np.asarray(freqs, dtype=np.float64)
    f = np.where(f <= 0.0, 1e-6, f)
    f2 = f * f
    numerator = 12194.0**2 * f2 * f2
    denominator = (
        (f2 + 20.6**2)
        * np.sqrt((f2 + 107.7**2) * (f2 + 737.9**2))
        * (f2 + 12194.0**2)
    )
    return 20.0 * np.log10(np.maximum(numerator / np.maximum(denominator, _TINY), _TINY)) + 2.0


def c_weight_db(freqs: np.ndarray | float) -> np.ndarray:
    """C 计权幅频响应（dB），1 kHz 处为 0 dB。"""
    f = np.asarray(freqs, dtype=np.float64)
    f = np.where(f <= 0.0, 1e-6, f)
    f2 = f * f
    numerator = 12194.0**2 * f2
    denominator = (f2 + 20.6**2) * (f2 + 12194.0**2)
    return 20.0 * np.log10(np.maximum(numerator / np.maximum(denominator, _TINY), _TINY)) + 0.06


def _design_sos(kind: str, sample_rate: int) -> np.ndarray:
    """设计计权 IIR（二阶节形式），并把 1 kHz 增益归一化到 1.0。"""
    if kind == "A":
        zeros = np.zeros(4, dtype=np.float64)
        poles = _A_POLES
    elif kind == "C":
        zeros = np.zeros(2, dtype=np.float64)
        poles = _C_POLES
    else:
        raise ValueError(f"kind 必须是 'A' 或 'C'，收到 {kind!r}")

    z, p, k = signal.bilinear_zpk(zeros, poles, 1.0, fs=sample_rate)
    sos = signal.zpk2sos(z, p, k)

    _, response = signal.sosfreqz(sos, worN=np.array([2.0 * np.pi * 1000.0 / sample_rate]))
    gain = abs(response[0])
    if gain <= 0:
        raise RuntimeError("计权滤波器设计失败：1 kHz 增益为 0")
    sos[0, :3] /= gain  # 只缩放第一节的分子，即可整体缩放增益
    return sos


class WeightingFilter:
    """流式计权滤波器，跨块保持状态。"""

    def __init__(self, kind: str, sample_rate: int) -> None:
        self.kind = kind
        self.sample_rate = int(sample_rate)
        self._sos = _design_sos(kind, self.sample_rate)
        self._zi = np.zeros((self._sos.shape[0], 2), dtype=np.float64)

    @property
    def sos(self) -> np.ndarray:
        return self._sos

    def process(self, block: np.ndarray) -> np.ndarray:
        data = np.asarray(block, dtype=np.float64)
        if data.size == 0:
            return data
        filtered, self._zi = signal.sosfilt(self._sos, data, zi=self._zi)
        return filtered

    def reset(self) -> None:
        self._zi = np.zeros_like(self._zi)

    def gain_at(self, freq: float) -> float:
        """该频率下的幅值增益（线性）。"""
        _, response = signal.sosfreqz(
            self._sos, worN=np.array([2.0 * np.pi * freq / self.sample_rate])
        )
        return float(abs(response[0]))
