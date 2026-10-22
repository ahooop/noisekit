"""一次可留证的测量会话。

把「写数据库 + 留证录音 + 阈值判定」缝在一个对象里，CLI 和图形界面都只调它。
两边各写一遍逻辑，迟早会有一边算错——这是这个类存在的唯一理由。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np

from .events.detector import NoiseEvent, Notification, ThresholdDetector
from .events.recorder import EventRecorder
from .metrics.meter import FrameMetrics
from .report.html_export import write_report
from .storage.query import SessionSummary, get_session, load_events, load_frames
from .storage.schema import connect
from .storage.writer import SessionWriter

DB_NAME = "session.db"
AUDIO_DIR = "audio"
REPORT_NAME = "report.html"


class RecordingSession:
    """在 ``root`` 目录下生成 session.db / audio/ / report.html。"""

    def __init__(
        self,
        root: str | Path,
        device_name: str,
        sample_rate: int,
        calibration_offset: float | None = None,
        threshold: float = 65.0,
        trigger_seconds: float = 3.0,
        pre_roll_seconds: float = 5.0,
        post_roll_seconds: float = 5.0,
        cooldown_seconds: float = 10.0,
        label: str | None = None,
        started_at: datetime | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.audio_dir = self.root / AUDIO_DIR
        self.db_path = self.root / DB_NAME
        self.threshold = float(threshold)
        self.pre_roll_seconds = float(pre_roll_seconds)
        self.post_roll_seconds = float(post_roll_seconds)
        self.sample_rate = int(sample_rate)

        self.writer = SessionWriter(self.db_path)
        self.session_id = self.writer.start_session(
            device_name=device_name,
            sample_rate=sample_rate,
            calibration_offset=calibration_offset,
            label=label,
            started_at=started_at,
        )
        self.recorder = EventRecorder(
            sample_rate=sample_rate,
            output_dir=self.audio_dir,
            pre_roll_seconds=pre_roll_seconds,
        )
        self.detector = ThresholdDetector(
            threshold=self.threshold,
            trigger_seconds=trigger_seconds,
            post_roll_seconds=post_roll_seconds,
            cooldown_seconds=cooldown_seconds,
        )
        self.events: list[NoiseEvent] = []
        self.last_ts = 0.0
        self._closed = False

    # ------------------------------------------------------------------ 主循环

    def feed(self, block: np.ndarray, frame: FrameMetrics) -> list[Notification]:
        """喂一个音频块及其指标，返回本步产生的事件通知。"""
        if self._closed:
            raise RuntimeError("会话已关闭")

        self.recorder.push(block)
        self.writer.add_frame(frame)
        self.last_ts = max(self.last_ts, frame.ts)

        notifications = []
        for note in self.detector.update(frame.display_level(), frame.ts):
            if note.kind == "start":
                self.recorder.begin()
            else:
                self.recorder.finish(note.event)
                self.writer.add_event(note.event, self.pre_roll_seconds, self.post_roll_seconds)
                self.events.append(note.event)
            notifications.append(note)
        return notifications

    # ------------------------------------------------------------------ 收尾

    def close(self) -> SessionSummary | None:
        """收尾：闭合未结束的事件、关录音、落盘、标记会话结束。"""
        if self._closed:
            return None
        note = self.detector.force_end(self.last_ts)
        if note is not None:
            self.recorder.finish(note.event)
            self.writer.add_event(note.event, self.pre_roll_seconds, self.post_roll_seconds)
            self.events.append(note.event)

        self.recorder.close()
        self.writer.end_session()
        self.writer.close()
        self._closed = True

        conn = connect(self.db_path)
        try:
            return get_session(conn, self.session_id)
        finally:
            conn.close()

    # ------------------------------------------------------------------ 导出

    def export_report(self, path: str | Path | None = None, title: str = "环境噪声测量报告") -> Path:
        target = Path(path) if path else self.root / REPORT_NAME
        conn = connect(self.db_path)
        try:
            summary = get_session(conn, self.session_id)
            frames = load_frames(conn, self.session_id)
            events = load_events(conn, self.session_id)
        finally:
            conn.close()
        if summary is None:
            raise RuntimeError(f"数据库里找不到会话 {self.session_id}")
        return write_report(target, summary, frames, events, title=title)

    def export_csv(self, path: str | Path | None = None) -> Path:
        from .report.csv_export import write_csv

        target = Path(path) if path else self.root / "metrics.csv"
        conn = connect(self.db_path)
        try:
            frames = load_frames(conn, self.session_id)
        finally:
            conn.close()
        return write_csv(target, frames)
