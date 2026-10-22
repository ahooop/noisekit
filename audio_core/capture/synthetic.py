"""合成信号源：测试与演示用，不需要麦克风。"""

from __future__ import annotations

import time
from collections.abc import Iterator

import numpy as np

KINDS = ("sine", "white")


class SyntheticSource:
    """生成正弦或高斯白噪。

    * ``kind="sine"``：``amplitude`` 是峰值幅度，满量程 1.0 对应 −3.01 dBFS；
    * ``kind="white"``：``amplitude`` 是标准差，读数约为 ``20·log10(amplitude)`` dBFS；
    * ``realtime=True`` 时按真实时间节奏产出，用于界面演示；测试里保持全速。
    """

    channels = 1

    def __init__(
        self,
        sample_rate: int = 48000,
        kind: str = "sine",
        freq: float = 1000.0,
        amplitude: float = 1.0,
        duration: float | None = None,
        seed: int = 0,
        realtime: bool = False,
    ) -> None:
        if kind not in KINDS:
            raise ValueError(f"kind 必须是 {KINDS} 之一，收到 {kind!r}")
        if sample_rate <= 0:
            raise ValueError("sample_rate 必须为正")
        self.sample_rate = int(sample_rate)
        self.kind = kind
        self.freq = float(freq)
        self.amplitude = float(amplitude)
        self.duration = duration
        self.realtime = realtime
        self.block_frames = max(256, round(0.01 * self.sample_rate))
        self._rng = np.random.default_rng(seed)
        self._phase = 0.0

    def _next_block(self, n: int) -> np.ndarray:
        if self.kind == "white":
            data = self._rng.standard_normal(n) * self.amplitude
            return np.clip(data, -1.0, 1.0).astype(np.float32)
        omega = 2.0 * np.pi * self.freq / self.sample_rate
        phases = self._phase + omega * np.arange(n)
        self._phase = float((self._phase + omega * n) % (2.0 * np.pi))
        return (self.amplitude * np.sin(phases)).astype(np.float32)

    def blocks(self) -> Iterator[np.ndarray]:
        total = None if self.duration is None else int(round(self.duration * self.sample_rate))
        produced = 0
        started = time.monotonic()
        while True:
            n = self.block_frames
            if total is not None:
                if produced >= total:
                    return
                n = min(n, total - produced)
            if self.realtime:
                delay = started + produced / self.sample_rate - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            yield self._next_block(n)
            produced += n

    def close(self) -> None:
        return None
