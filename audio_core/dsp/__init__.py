"""数字信号处理：分帧、计权、时间计权、电平换算、频谱。"""

from .framing import block_frames, mean_square, peak_amplitude, remove_dc
from .level import (
    DB_FLOOR,
    amplitude_to_db,
    calibration_offset,
    dbfs_to_spl,
    energy_mean_db,
    mean_square_to_db,
)
from .spectrum import dominant_frequency, spectrum_db
from .time_weight import TimeWeighter, fast_weighter, impulse_weighter, slow_weighter
from .weighting import WeightingFilter, a_weight_db, c_weight_db

__all__ = [
    "DB_FLOOR",
    "TimeWeighter",
    "WeightingFilter",
    "a_weight_db",
    "amplitude_to_db",
    "block_frames",
    "c_weight_db",
    "calibration_offset",
    "dbfs_to_spl",
    "dominant_frequency",
    "energy_mean_db",
    "fast_weighter",
    "impulse_weighter",
    "mean_square",
    "mean_square_to_db",
    "peak_amplitude",
    "remove_dc",
    "slow_weighter",
    "spectrum_db",
]
