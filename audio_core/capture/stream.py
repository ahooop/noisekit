"""真实设备采集。

PortAudio 回调线程里只做一件事：把样本 ``write`` 进环形缓冲。任何分配、日志、
计算都不允许出现在回调里，否则 24 小时长跑必然掉帧（设计文档 §7）。
"""

from __future__ import annotations

import threading
import time

import numpy as np

from .ring import RingBuffer
from .source import SourceError

CANDIDATE_RATES = (48000, 44100)


class SoundDeviceSource:
    """把 sounddevice 的输入流包装成 ``AudioSource``。"""

    channels = 1

    def __init__(
        self,
        device: int | str | None = None,
        sample_rate: int | None = None,
        ring_seconds: float = 10.0,
    ) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:
            raise SourceError(f"音频后端不可用：{exc}。请先 pip install sounddevice") from exc
        self._sd = sd
        self.device = device
        self._requested_rate = sample_rate
        self.sample_rate = self._negotiate_rate(sample_rate, device)
        self.block_frames = max(256, round(0.01 * self.sample_rate))
        self._ring = RingBuffer(capacity=int(ring_seconds * self.sample_rate))
        self._closed = threading.Event()
        self._error: str | None = None
        self._callback_status: list[str] = []
        self._stream = None
        self._open()

    # ---------------------------------------------------------------- 协商

    def _negotiate_rate(self, requested: int | None, device: int | str | None) -> int:
        candidates: list[int] = []
        if requested:
            candidates.append(int(requested))
        candidates.extend(CANDIDATE_RATES)
        try:
            default_rate = int(self._sd.query_devices(device, "input")["default_samplerate"])
        except Exception:
            default_rate = 0
        if default_rate and default_rate not in candidates:
            candidates.append(default_rate)

        attempts: list[str] = []
        for rate in candidates:
            try:
                self._sd.check_input_settings(
                    device=device, samplerate=rate, channels=1, dtype="float32"
                )
                return rate
            except Exception as exc:
                attempts.append(f"{rate} Hz: {exc}")
        raise SourceError("没有可用的采样率，尝试过：\n  " + "\n  ".join(attempts))

    # ---------------------------------------------------------------- 采集

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            # 溢出/欠载只记账，不在回调里打日志
            self._callback_status.append(str(status))
            del self._callback_status[:-20]
            self._error = str(status) if "overflow" in str(status).lower() else self._error
        self._ring.write(indata[:, 0] if indata.ndim > 1 else indata)

    def _open(self) -> None:
        try:
            self._stream = self._sd.InputStream(
                device=self.device,
                channels=1,
                samplerate=self.sample_rate,
                blocksize=self.block_frames,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            raise SourceError(f"无法打开输入流：{exc}") from exc

    def blocks(self):
        pending = np.empty(0, dtype=np.float32)
        while not self._closed.is_set():
            chunk = self._ring.read(self.block_frames * 4)
            if chunk.size == 0:
                time.sleep(0.005)
                continue
            pending = np.concatenate((pending, chunk)) if pending.size else chunk
            while pending.size >= self.block_frames:
                yield pending[: self.block_frames]
                pending = pending[self.block_frames :]

    # ---------------------------------------------------------------- 状态

    @property
    def status_text(self) -> str:
        return self._callback_status[-1] if self._callback_status else ""

    def close(self) -> None:
        self._closed.set()
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
