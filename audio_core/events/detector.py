"""阈值告警状态机（纯函数，可脱离麦克风测试）。

规则（设计文档 §3.1）：

* 超过阈值并**持续** ``trigger_seconds`` 才触发，避免拍桌子就报警；
* 触发后一直保持到电平回落到阈值以下并持续 ``post_roll_seconds``；
* 结束之后 ``cooldown_seconds`` 内不再触发，避免同一段噪音被切成十几个事件。

``ended_at`` 记的是「最后一次超过阈值」的时刻，不含后置缓冲；
后置缓冲由录音器负责，两者分开才说得清「噪音持续多久」和「音频保存多长」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class State(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    COOLDOWN = "cooldown"


@dataclass
class NoiseEvent:
    started_at: float
    threshold: float
    peak: float
    ended_at: float | None = None
    audio_path: str | None = None

    @property
    def duration(self) -> float:
        if self.ended_at is None:
            return 0.0
        return max(self.ended_at - self.started_at, 0.0)


@dataclass(frozen=True)
class Notification:
    kind: str  # "start" | "end"
    event: NoiseEvent


@dataclass
class ThresholdDetector:
    threshold: float = 65.0
    trigger_seconds: float = 3.0
    post_roll_seconds: float = 5.0
    cooldown_seconds: float = 10.0
    state: State = field(default=State.IDLE, init=False)

    _above_since: float | None = field(default=None, init=False, repr=False)
    _last_above: float | None = field(default=None, init=False, repr=False)
    _cooldown_until: float = field(default=0.0, init=False, repr=False)
    _current: NoiseEvent | None = field(default=None, init=False, repr=False)
    # 触发前的「待定峰值」：最响的那一下往往发生在等满 trigger_seconds 之前，
    # 只在触发时刻取当前电平会系统性低估。
    _pending_peak: float = field(default=float("-inf"), init=False, repr=False)

    def __post_init__(self) -> None:
        if self.trigger_seconds < 0:
            raise ValueError("trigger_seconds 不能为负")
        if self.post_roll_seconds < 0 or self.cooldown_seconds < 0:
            raise ValueError("后置缓冲与冷却时间不能为负")

    def update(self, level: float, timestamp: float) -> list[Notification]:
        """喂一个电平样本，返回本步产生的事件通知（0～1 条）。"""
        notifications: list[Notification] = []

        if self.state is State.COOLDOWN and timestamp >= self._cooldown_until:
            self.state = State.IDLE
            self._above_since = None
            self._pending_peak = float("-inf")

        if self.state is State.IDLE:
            if level < self.threshold:
                self._above_since = None
                self._pending_peak = float("-inf")
                return notifications
            if self._above_since is None:
                self._above_since = timestamp
                self._pending_peak = level
            else:
                self._pending_peak = max(self._pending_peak, level)
            if timestamp - self._above_since >= self.trigger_seconds:
                event = NoiseEvent(
                    started_at=self._above_since,
                    threshold=self.threshold,
                    peak=max(self._pending_peak, level),
                )
                self._current = event
                self.state = State.ACTIVE
                self._last_above = timestamp
                self._pending_peak = float("-inf")
                notifications.append(Notification("start", event))
            return notifications

        if self.state is State.ACTIVE:
            event = self._current
            assert event is not None
            event.peak = max(event.peak, level)
            if level >= self.threshold:
                self._last_above = timestamp
            elif self._last_above is not None and timestamp - self._last_above >= self.post_roll_seconds:
                event.ended_at = self._last_above
                self.state = State.COOLDOWN
                self._cooldown_until = max(timestamp, self._last_above + self.cooldown_seconds)
                self._current = None
                self._above_since = None
                notifications.append(Notification("end", event))
        return notifications

    def force_end(self, timestamp: float) -> Notification | None:
        """会话结束时收尾，避免最后一段噪音永远不闭合。"""
        if self.state is not State.ACTIVE or self._current is None:
            return None
        event = self._current
        event.ended_at = max(self._last_above or timestamp, event.started_at)
        self.state = State.IDLE
        self._current = None
        self._above_since = None
        self._pending_peak = float("-inf")
        return Notification("end", event)
