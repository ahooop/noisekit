"""电平换算与校准。

约定（设计文档 §4.2）：

* ``dBFS = 10·log10(mean_square)``，满量程正弦（±1.0）≈ −3.01 dBFS；
* ``dB SPL = dBFS + offset``；``offset is None`` 表示未校准，读数一律标「相对」；
* 所有换算都做了下限保护，全零输入返回 -200 dB 而不是 -inf / NaN。
"""

from __future__ import annotations

import math

MIN_MEAN_SQUARE = 1e-20  # 对应 -200 dB，低于消费级麦克风的噪声底
DB_FLOOR = -200.0


def mean_square_to_db(mean_square: float) -> float:
    if not math.isfinite(mean_square) or mean_square <= MIN_MEAN_SQUARE:
        return DB_FLOOR
    return 10.0 * math.log10(mean_square)


def amplitude_to_db(amplitude: float) -> float:
    """峰值幅度换算 dBFS（20·log10）。"""
    value = abs(float(amplitude))
    if not math.isfinite(value) or value <= 1e-10:
        return DB_FLOOR
    return max(20.0 * math.log10(value), DB_FLOOR)


def dbfs_to_spl(dbfs: float, offset: float | None) -> float | None:
    """未校准时返回 None——宁可没有数，也不要给一个假的绝对值。"""
    if offset is None:
        return None
    if dbfs <= DB_FLOOR:
        return None
    return dbfs + float(offset)


def calibration_offset(reference_spl: float, measured_dbfs: float) -> float:
    """由「参考声压级」与「当前读数」反算校准偏移。"""
    if measured_dbfs <= DB_FLOOR:
        raise ValueError("当前读数过低，无法校准；请确认麦克风在工作且不在静音")
    return float(reference_spl) - float(measured_dbfs)


def energy_mean_db(levels_ms: list[float]) -> float:
    """一组均方值的能量平均（用于 Leq）。"""
    if not levels_ms:
        return DB_FLOOR
    return mean_square_to_db(sum(levels_ms) / len(levels_ms))
