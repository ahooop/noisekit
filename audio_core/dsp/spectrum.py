"""频谱分析：加窗、单边谱、dB 换算。

输出的 dB 是「峰值幅度 dBFS」：满量程正弦在该频率的谱峰读数为 0 dBFS。
界面与报告共用这一个实现，避免两处刻度对不上。
"""

from __future__ import annotations

import numpy as np
from scipy import signal

DEFAULT_N_FFT = 2048
_TINY = 1e-12


def spectrum_db(
    block: np.ndarray,
    sample_rate: int,
    n_fft: int = DEFAULT_N_FFT,
    window: str = "hann",
) -> tuple[np.ndarray, np.ndarray]:
    """返回 ``(freqs, db)``；不足 ``n_fft`` 时补零，超出取最后 ``n_fft`` 个样本。"""
    data = np.asarray(block, dtype=np.float64).ravel()
    if data.size == 0:
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
        return freqs, np.full(freqs.shape, -120.0)

    if data.size > n_fft:
        data = data[-n_fft:]
    win = signal.get_window(window, data.size, fftbins=True)
    coherent_gain = float(np.sum(win))
    if coherent_gain <= 0:
        coherent_gain = 1.0

    spectrum = np.fft.rfft(data * win, n=n_fft)
    amplitude = 2.0 * np.abs(spectrum) / coherent_gain
    amplitude[0] *= 0.5  # 直流分量不该翻倍
    db = 20.0 * np.log10(np.maximum(amplitude, _TINY))
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    return freqs, db


def dominant_frequency(block: np.ndarray, sample_rate: int, n_fft: int = DEFAULT_N_FFT) -> float:
    """谱峰对应频率，用于自检（例如确认 1 kHz 正弦真的在 1 kHz）。"""
    freqs, db = spectrum_db(block, sample_rate, n_fft=n_fft)
    if freqs.size <= 1:
        return 0.0
    return float(freqs[int(np.argmax(db[1:])) + 1])
