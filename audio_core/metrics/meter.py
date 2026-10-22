"""电声指标：块 → FrameMetrics。

这是整个引擎的汇合点：计权滤波、时间计权、Leq 窗口、峰值跟踪都在这里。
界面、存储、报告只消费 ``FrameMetrics``，不自己算任何声学量。
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

from ..dsp.framing import block_frames, mean_square, peak_amplitude, remove_dc
from ..dsp.level import (
    DB_FLOOR,
    amplitude_to_db,
    dbfs_to_spl,
    mean_square_to_db,
)
from ..dsp.time_weight import fast_weighter, slow_weighter
from ..dsp.weighting import WeightingFilter

HISTORY_SECONDS = 10.0
LEQ_REFRESH_SECONDS = 0.1


@dataclass(frozen=True, slots=True)
class FrameMetrics:
    """一个 10 ms 块的测量结果。"""

    ts: float  # 会话内相对秒
    dbfs: float  # 未计权
    db_a: float  # A 计权瞬时
    db_c: float  # C 计权瞬时
    laf: float  # A + Fast 时间计权
    las: float  # A + Slow 时间计权
    leq_1s: float
    leq_10s: float
    leq_session: float
    lafmax: float
    lcpeak: float
    spl: float | None = None
    spl_a: float | None = None
    spl_c: float | None = None

    def as_dict(self) -> dict[str, float | None]:
        return asdict(self)

    @property
    def calibrated(self) -> bool:
        return self.spl_a is not None

    def display_level(self) -> float:
        """界面主数字：校准时用 dB(A) SPL，否则用 A 计权 dBFS。"""
        return self.spl_a if self.spl_a is not None else self.db_a


class SoundLevelMeter:
    """把连续的音频块变成连续的电声指标流。"""

    def __init__(self, sample_rate: int, calibration_offset: float | None = None) -> None:
        self.sample_rate = int(sample_rate)
        self.block_frames = block_frames(self.sample_rate)
        self.dt = self.block_frames / self.sample_rate
        self.calibration_offset = calibration_offset if calibration_offset is None else float(
            calibration_offset
        )

        self._a = WeightingFilter("A", self.sample_rate)
        self._c = WeightingFilter("C", self.sample_rate)
        self._fast = fast_weighter(self.dt)
        self._slow = slow_weighter(self.dt)

        self._history: deque[tuple[float, float]] = deque(
            maxlen=int(HISTORY_SECONDS / self.dt) + 2
        )
        self._session_energy = 0.0
        self._session_blocks = 0
        self._lafmax = DB_FLOOR
        self._lcpeak_amplitude = 0.0
        self._leq_1s = DB_FLOOR
        self._leq_10s = DB_FLOOR
        self._leq_1s_ts = float("-inf")
        self._leq_10s_ts = float("-inf")

    # ---------------------------------------------------------------- 主流程

    def process(self, block, timestamp: float) -> FrameMetrics:
        raw = remove_dc(block)
        if raw.size == 0:
            raise ValueError("空音频块")

        a_signal = self._a.process(raw)
        c_signal = self._c.process(raw)

        ms_raw = mean_square(raw)
        ms_a = mean_square(a_signal)
        ms_c = mean_square(c_signal)

        laf_ms = self._fast.update(ms_a)
        las_ms = self._slow.update(ms_a)

        self._history.append((timestamp, ms_a))
        cutoff = timestamp - HISTORY_SECONDS
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        self._session_energy += ms_a * self.dt
        self._session_blocks += 1

        laf_db = mean_square_to_db(laf_ms)
        self._lafmax = max(self._lafmax, laf_db)

        peak_amp = peak_amplitude(c_signal)
        if peak_amp > self._lcpeak_amplitude:
            self._lcpeak_amplitude = peak_amp

        leq_1s = self._window_leq(timestamp, 1.0, "_leq_1s_ts", "_leq_1s")
        leq_10s = self._window_leq(timestamp, HISTORY_SECONDS, "_leq_10s_ts", "_leq_10s")

        session_seconds = self._session_blocks * self.dt
        leq_session = (
            mean_square_to_db(self._session_energy / session_seconds) if session_seconds > 0 else DB_FLOOR
        )

        db_a = mean_square_to_db(ms_a)
        db_c = mean_square_to_db(ms_c)
        return FrameMetrics(
            ts=timestamp,
            dbfs=mean_square_to_db(ms_raw),
            db_a=db_a,
            db_c=db_c,
            laf=laf_db,
            las=mean_square_to_db(las_ms),
            leq_1s=leq_1s,
            leq_10s=leq_10s,
            leq_session=leq_session,
            lafmax=self._lafmax,
            lcpeak=amplitude_to_db(self._lcpeak_amplitude),
            spl=dbfs_to_spl(mean_square_to_db(ms_raw), self.calibration_offset),
            spl_a=dbfs_to_spl(db_a, self.calibration_offset),
            spl_c=dbfs_to_spl(db_c, self.calibration_offset),
        )

    # ---------------------------------------------------------------- 辅助

    def _window_leq(self, timestamp: float, window: float, stamp_attr: str, value_attr: str) -> float:
        """能量平均；按 LEQ_REFRESH_SECONDS 节流，避免每块都扫一遍窗口。"""
        last = getattr(self, stamp_attr)
        if timestamp - last >= LEQ_REFRESH_SECONDS or last == float("-inf"):
            cutoff = timestamp - window
            total = 0.0
            count = 0
            for ts, ms in reversed(self._history):
                if ts < cutoff:
                    break
                total += ms
                count += 1
            value = mean_square_to_db(total / count) if count else DB_FLOOR
            setattr(self, value_attr, value)
            setattr(self, stamp_attr, timestamp)
        return getattr(self, value_attr)

    @property
    def lafmax(self) -> float:
        return self._lafmax

    @property
    def lcpeak(self) -> float:
        return amplitude_to_db(self._lcpeak_amplitude)

    def reset(self) -> None:
        self._a.reset()
        self._c.reset()
        self._fast.reset()
        self._slow.reset()
        self._history.clear()
        self._session_energy = 0.0
        self._session_blocks = 0
        self._lafmax = DB_FLOOR
        self._lcpeak_amplitude = 0.0
        self._leq_1s = DB_FLOOR
        self._leq_10s = DB_FLOOR
        self._leq_1s_ts = float("-inf")
        self._leq_10s_ts = float("-inf")
