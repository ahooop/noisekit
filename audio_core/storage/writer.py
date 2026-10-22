"""会话落盘：独立线程批量写，绝不阻塞采集。

为什么必须批量：SQLite 每帧一次 commit，等于每 100 ms 一次 fsync，
在机械盘上会直接把采集回调拖垮。这里攒够 100 帧或 2 秒提交一次。
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime
from pathlib import Path

from ..metrics.meter import FrameMetrics
from .schema import connect, init_db

INSERT_FRAME = """
    INSERT INTO frames
        (session_id, ts, dbfs, db_a, db_c, spl, db_spl_a, db_spl_c, leq_1s, leq_10s, lafmax, lcpeak)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_EVENT = """
    INSERT INTO events
        (session_id, started_at, ended_at, threshold, peak_db_a, audio_path, pre_roll, post_roll)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


class SessionWriter:
    """一个会话写一个数据库；内部一个写线程。"""

    def __init__(
        self,
        db_path: str | Path,
        batch_size: int = 100,
        flush_interval: float = 2.0,
    ) -> None:
        self.db_path = Path(db_path)
        self.batch_size = max(int(batch_size), 1)
        self.flush_interval = float(flush_interval)

        self._conn = connect(self.db_path)
        init_db(self._conn)
        self._lock = threading.Lock()
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="noisekit-writer", daemon=True)
        self._running = False

        self.session_id: int | None = None
        self.frames_written = 0
        self.events_written = 0

    # ------------------------------------------------------------------ 会话

    def start_session(
        self,
        device_name: str,
        sample_rate: int,
        calibration_offset: float | None = None,
        label: str | None = None,
        started_at: datetime | None = None,
    ) -> int:
        started = (started_at or datetime.now()).isoformat(timespec="seconds")
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO sessions (started_at, device_name, sample_rate, calibration_offset, label)"
                " VALUES (?, ?, ?, ?, ?)",
                (started, device_name, int(sample_rate), calibration_offset, label),
            )
            self._conn.commit()
            self.session_id = int(cursor.lastrowid)
        self._ensure_thread()
        return self.session_id

    def end_session(self) -> None:
        if self.session_id is None:
            return
        self.flush()
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
                (datetime.now().isoformat(timespec="seconds"), self.session_id),
            )
            self._conn.commit()

    # ------------------------------------------------------------------ 写入

    def add_frame(self, frame: FrameMetrics) -> None:
        if self.session_id is None:
            raise RuntimeError("还没有开始会话")
        self._queue.put(
            (
                "frame",
                (
                    self.session_id,
                    frame.ts,
                    frame.dbfs,
                    frame.db_a,
                    frame.db_c,
                    frame.spl,
                    frame.spl_a,
                    frame.spl_c,
                    frame.leq_1s,
                    frame.leq_10s,
                    frame.lafmax,
                    frame.lcpeak,
                ),
            )
        )

    def add_event(self, event, pre_roll: float = 5.0, post_roll: float | None = None) -> None:
        if self.session_id is None:
            raise RuntimeError("还没有开始会话")
        self._queue.put(
            (
                "event",
                (
                    self.session_id,
                    event.started_at,
                    event.ended_at,
                    event.threshold,
                    event.peak,
                    event.audio_path,
                    pre_roll,
                    post_roll,
                ),
            )
        )

    def flush(self) -> None:
        """等待队列里的数据真正落盘（导出报告前必须调用）。"""
        if not self._running:
            self._drain()
            return
        done = threading.Event()
        self._queue.put(("flush", done))
        done.wait(timeout=10.0)

    # ------------------------------------------------------------------ 线程

    def _ensure_thread(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread.start()

    def _run(self) -> None:  # pragma: no cover - 线程主体，逻辑由 _drain 覆盖
        while True:
            try:
                item = self._queue.get(timeout=self.flush_interval)
            except queue.Empty:
                self._drain()
                continue
            kind = item[0]
            if kind == "stop":
                self._drain()
                return
            if kind == "flush":
                self._drain()
                done = item[1]
                if isinstance(done, threading.Event):
                    done.set()
                continue
            self._drain_with(item)

    def _drain_with(self, first: tuple[str, object]) -> None:
        batch = [first]
        while True:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        self._write(batch)

    def _drain(self) -> None:
        batch = []
        while True:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self._write(batch)

    def _write(self, batch: list[tuple[str, object]]) -> None:
        frames = []
        events = []
        leftover = []
        for kind, payload in batch:
            if kind == "frame":
                frames.append(payload)
            elif kind == "event":
                events.append(payload)
            else:
                leftover.append((kind, payload))

        if frames or events:
            with self._lock:
                if frames:
                    self._conn.executemany(INSERT_FRAME, frames)
                if events:
                    self._conn.executemany(INSERT_EVENT, events)
                self._conn.commit()
                self.frames_written += len(frames)
                self.events_written += len(events)

        for item in leftover:
            if item[0] == "flush":
                done = item[1]
                if isinstance(done, threading.Event):
                    done.set()

    # ------------------------------------------------------------------ 收尾

    def close(self) -> None:
        if self._running:
            self._queue.put(("stop", None))
            self._thread.join(timeout=10.0)
            self._running = False
        else:
            self._drain()
        with self._lock:
            self._conn.close()

    def __enter__(self) -> SessionWriter:
        return self

    def __exit__(self, *exc_info) -> None:
        self.end_session()
        self.close()
