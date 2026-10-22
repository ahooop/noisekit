"""WAV 文件回放源。

两个用途：

1. 测试里用它驱动完整链路，验证「同一段录音 → 同样的指标」；
2. 事后复算：对已留证的录音重新算一遍声级。

``realtime=False`` 时全速回放，测试无需真的等 10 秒。
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np


class WavFileSource:
    channels = 1

    def __init__(self, path: str | Path, realtime: bool = False, gain: float = 1.0) -> None:
        from scipy.io import wavfile

        self.path = Path(path)
        self.realtime = realtime
        self.gain = float(gain)
        try:
            fs, raw = wavfile.read(self.path)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"找不到音频文件: {self.path}") from exc
        except Exception as exc:  # scipy 抛出的类型不稳定
            raise ValueError(f"无法解析 WAV: {self.path} ({exc})") from exc

        data = self._to_float(raw)
        if data.ndim > 1:
            data = data.mean(axis=1)  # 多声道混成单声道
        self.sample_rate = int(fs)
        self._data = np.ascontiguousarray(data, dtype=np.float32) * self.gain
        self.block_frames = max(256, round(0.01 * self.sample_rate))

    @staticmethod
    def _to_float(raw: np.ndarray) -> np.ndarray:
        if raw.dtype == np.int16:
            return raw.astype(np.float32) / 32768.0
        if raw.dtype == np.int32:
            return raw.astype(np.float32) / 2147483648.0
        if raw.dtype == np.uint8:
            return (raw.astype(np.float32) - 128.0) / 128.0
        return raw.astype(np.float32)

    @property
    def duration(self) -> float:
        return len(self._data) / self.sample_rate

    def blocks(self) -> Iterator[np.ndarray]:
        frames = self._data
        n_total = len(frames)
        step = self.block_frames
        start = 0
        t0 = time.monotonic()
        sent = 0
        while start < n_total:
            end = min(start + step, n_total)
            if self.realtime:
                target = t0 + sent / self.sample_rate
                delay = target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            yield frames[start:end]
            sent += end - start
            start = end

    def close(self) -> None:
        return None
