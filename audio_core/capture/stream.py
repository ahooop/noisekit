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
        idle_timeout: float | None = 3.0,
    ) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:
            raise SourceError(f"音频后端不可用：{exc}。请先 pip install sounddevice") from exc
        self._sd = sd
        self.device = self._resolve_device(device)
        self._requested_rate = sample_rate
        self.idle_timeout = idle_timeout
        self.sample_rate = self._negotiate_rate(sample_rate, self.device)
        self.block_frames = max(256, round(0.01 * self.sample_rate))
        self._ring = RingBuffer(capacity=int(ring_seconds * self.sample_rate))
        self._closed = threading.Event()
        self._error: str | None = None
        self._callback_status: list[str] = []
        self._stream = None
        self._open()

    # ---------------------------------------------------------------- 协商

    def _resolve_device(self, device: int | str | None) -> int | str:
        """没指定设备时，退到系统默认输入；系统没设默认输入就退到第一个可用输入。

        Windows 上经常出现 ``sd.default.device[0] == -1``（没设默认录音设备），
        这时如果直接开流，用户只会看到「Error querying device -1」。
        """
        if device is not None:
            return device
        try:
            default_in = int(self._sd.default.device[0])
        except Exception:
            default_in = -1
        if default_in >= 0:
            return default_in
        for index, info in enumerate(self._sd.query_devices()):
            if int(info.get("max_input_channels", 0)) > 0:
                return index
        raise SourceError(
            "没有可用的输入设备。请确认麦克风已被系统识别，"
            "或用 --list-devices 查看设备、--device 指定序号。"
        )

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
        raise SourceError(
            f"设备 {device!r} 没有可用的采样率，尝试过：\n  "
            + "\n  ".join(attempts)
            + "\n可用 --list-devices 查看设备，用 --device 指定序号。"
        )

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
        last_data = time.monotonic()
        while not self._closed.is_set():
            chunk = self._ring.read(self.block_frames * 4)
            if chunk.size == 0:
                # 设备打开成功但一个回调都没来（拔掉、被独占、虚拟设备不发数据），
                # 必须报错而不是永远空转——否则用户看到的是「程序卡死」。
                if self.idle_timeout and time.monotonic() - last_data > self.idle_timeout:
                    raise SourceError(
                        f"设备 {self.device} 已打开，但 {self.idle_timeout:.0f} 秒内没有收到任何音频。"
                        "请检查麦克风是否被占用、是否被系统静音，或换一个设备。"
                    )
                time.sleep(0.005)
                continue
            last_data = time.monotonic()
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
