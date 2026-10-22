"""时间计权：Fast / Slow / Impulse（IEC 61672-1）。"""

from __future__ import annotations

import math


class TimeWeighter:
    """对能量（均方值）做一阶指数平均。

    在均方域上做而不是在 dB 域上做，否则平均出来的不是能量平均，
    Leq 与 LAF 会系统性偏低。
    """

    def __init__(self, tau_s: float, dt_s: float, tau_fall_s: float | None = None) -> None:
        if tau_s <= 0 or dt_s <= 0:
            raise ValueError("时间常数与步长必须为正")
        self.tau_s = float(tau_s)
        self.tau_fall_s = float(tau_fall_s) if tau_fall_s else self.tau_s
        self.dt_s = float(dt_s)
        self._alpha_up = 1.0 - math.exp(-dt_s / self.tau_s)
        self._alpha_down = 1.0 - math.exp(-dt_s / self.tau_fall_s)
        self._value: float | None = None

    @property
    def value(self) -> float:
        return self._value or 0.0

    def update(self, mean_square: float) -> float:
        current = max(float(mean_square), 0.0)
        if self._value is None:
            self._value = current
        else:
            alpha = self._alpha_up if current >= self._value else self._alpha_down
            self._value = alpha * current + (1.0 - alpha) * self._value
        return self._value

    def reset(self) -> None:
        self._value = None


def fast_weighter(dt_s: float) -> TimeWeighter:
    return TimeWeighter(0.125, dt_s)


def slow_weighter(dt_s: float) -> TimeWeighter:
    return TimeWeighter(1.0, dt_s)


def impulse_weighter(dt_s: float) -> TimeWeighter:
    """Impulse：上升 35 ms、下降 1500 ms。"""
    return TimeWeighter(0.035, dt_s, tau_fall_s=1.5)
