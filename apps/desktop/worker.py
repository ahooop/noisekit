"""分析工作线程：采集 → 分析 → 分发给界面。

设计文档 §7 的两条硬约束在这里落地：

* 界面**不追帧**：信号按 30 fps 限速，积压时丢中间帧，绝不让 UI 阻塞采集；
* 降采样由这里做，界面拿到的一定是「最新」的快照。
"""

from __future__ import annotations

import contextlib
import threading
import time

import numpy as np
from PySide6.QtCore import QThread, Signal

from audio_core.analyzers.noise import NoiseAnalyzer
from audio_core.dsp.spectrum import spectrum_db

SPECTRUM_FRAMES = 2048
SPECTRUM_INTERVAL = 0.1


class AnalysisWorker(QThread):
    frame_ready = Signal(object)  # FrameMetrics
    spectrum_ready = Signal(object, object)  # freqs, db
    event_ready = Signal(str, object)  # kind("start"/"end"), NoiseEvent
    failed = Signal(str)
    stopped = Signal(float)  # 分析过的音频秒数

    def __init__(
        self,
        source,
        calibration_offset: float | None = None,
        fps: float = 30.0,
        session=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source = source
        self.calibration_offset = calibration_offset
        self.session = session
        self.min_interval = 1.0 / max(fps, 1.0)
        self._stop = threading.Event()
        self._audio_tail = np.zeros(SPECTRUM_FRAMES, dtype=np.float32)

    def stop(self) -> None:
        self._stop.set()
        with contextlib.suppress(Exception):
            self.source.close()

    def run(self) -> None:  # noqa: C901 - 主循环，保持扁平即可
        sample_rate = self.source.sample_rate
        analyzer = NoiseAnalyzer(sample_rate, calibration_offset=self.calibration_offset)
        consumed = 0
        last_frame_emit = 0.0
        last_spectrum_emit = 0.0
        try:
            for block in self.source.blocks():
                if self._stop.is_set():
                    break
                frame = analyzer.process_frame(block, consumed / sample_rate)
                consumed += int(block.size)

                if self.session is not None:
                    for note in self.session.feed(block, frame):
                        self.event_ready.emit(note.kind, note.event)

                self._audio_tail = np.concatenate((self._audio_tail, block))[-SPECTRUM_FRAMES:]

                now = time.monotonic()
                if now - last_frame_emit >= self.min_interval:
                    last_frame_emit = now
                    self.frame_ready.emit(frame)
                if now - last_spectrum_emit >= SPECTRUM_INTERVAL:
                    last_spectrum_emit = now
                    freqs, db = spectrum_db(self._audio_tail, sample_rate)
                    self.spectrum_ready.emit(freqs, db)
        except Exception as exc:  # 采集层任何故障都要变成人能看懂的一句话
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            with contextlib.suppress(Exception):
                self.source.close()
            self.stopped.emit(consumed / sample_rate if sample_rate else 0.0)
