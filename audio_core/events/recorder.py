"""告警留证录音：前置缓冲 + 事件音频。

为什么非要前置缓冲：等超过阈值才开始录，录到的第一秒往往已经被削掉，
回放只剩「响声的尾巴」，这在真实纠纷里等于没有证据。
"""

from __future__ import annotations

import wave
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np

PRE_ROLL_DEFAULT = 5.0


class EventRecorder:
    """维护一段滚动的前置缓冲，事件触发时连同缓冲一起落盘。"""

    def __init__(
        self,
        sample_rate: int,
        output_dir: str | Path,
        pre_roll_seconds: float = PRE_ROLL_DEFAULT,
        name_prefix: str = "event",
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.output_dir = Path(output_dir)
        self.pre_roll_seconds = float(pre_roll_seconds)
        self.name_prefix = name_prefix

        self._pre_roll: deque[np.ndarray] = deque()
        self._pre_roll_samples = 0
        self._max_pre_roll = int(pre_roll_seconds * self.sample_rate)

        self._handle: wave.Wave_write | None = None
        self._current_path: Path | None = None
        self.samples_written = 0

    # ------------------------------------------------------------------ 状态

    @property
    def recording(self) -> bool:
        return self._handle is not None

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    # ------------------------------------------------------------------ 采集

    def push(self, block: np.ndarray) -> None:
        """持续喂入音频。空闲时维护前置缓冲，录制时同时写盘。"""
        data = np.asarray(block, dtype=np.float32).ravel()
        if data.size == 0:
            return

        if self.recording:
            self._write(data)
        self._push_pre_roll(data)

    def _push_pre_roll(self, data: np.ndarray) -> None:
        if self._max_pre_roll <= 0:
            return
        self._pre_roll.append(data.copy())
        self._pre_roll_samples += data.size
        while self._pre_roll and self._pre_roll_samples - self._pre_roll[0].size >= self._max_pre_roll:
            dropped = self._pre_roll.popleft()
            self._pre_roll_samples -= dropped.size

    # ------------------------------------------------------------------ 录制

    def begin(self, timestamp: float | None = None) -> Path:
        """开始录制，把前置缓冲先写进去。"""
        if self.recording:
            return self._current_path  # type: ignore[return-value]

        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.output_dir / f"{self.name_prefix}_{stamp}.wav"
        suffix = 1
        while path.exists():
            path = self.output_dir / f"{self.name_prefix}_{stamp}_{suffix}.wav"
            suffix += 1

        # 句柄要跨 push() 调用保持打开，不能用 with
        handle = wave.open(str(path), "wb")  # noqa: SIM115
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(self.sample_rate)
        self._handle = handle
        self._current_path = path
        self.samples_written = 0

        for chunk in self._pre_roll:
            self._write(chunk)
        self._pre_roll.clear()
        self._pre_roll_samples = 0
        return path

    def finish(self, event=None) -> Path | None:
        """结束录制并返回文件路径。"""
        if not self.recording:
            return None
        path = self._current_path
        try:
            self._handle.close()  # type: ignore[union-attr]
        finally:
            self._handle = None
            self._current_path = None
        if event is not None:
            event.audio_path = str(path) if path else None
        return path

    def _write(self, data: np.ndarray) -> None:
        handle = self._handle
        if handle is None:
            return
        clipped = np.clip(data, -1.0, 1.0)
        handle.writeframes((clipped * 32767.0).astype("<i2").tobytes())
        self.samples_written += int(data.size)

    def close(self) -> None:
        if self.recording:
            self.finish()
