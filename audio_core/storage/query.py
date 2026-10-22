"""读取会话数据。

`ended_at IS NULL` 的会话就是「上次没正常退出」——崩溃、断电、被任务管理器杀掉。
它的数据依然可读、可导出，只是要告诉用户这段话没跑完。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..events.detector import NoiseEvent
from ..metrics.meter import FrameMetrics


@dataclass(frozen=True)
class SessionSummary:
    id: int
    started_at: str
    ended_at: str | None
    device_name: str | None
    sample_rate: int
    calibration_offset: float | None
    label: str | None
    frame_count: int
    event_count: int

    @property
    def finished(self) -> bool:
        return self.ended_at is not None


def list_sessions(conn: sqlite3.Connection) -> list[SessionSummary]:
    rows = conn.execute(
        """
        SELECT s.*,
               (SELECT COUNT(*) FROM frames f WHERE f.session_id = s.id) AS frame_count,
               (SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) AS event_count
        FROM sessions s
        ORDER BY s.id DESC
        """
    ).fetchall()
    return [
        SessionSummary(
            id=row["id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            device_name=row["device_name"],
            sample_rate=row["sample_rate"],
            calibration_offset=row["calibration_offset"],
            label=row["label"],
            frame_count=row["frame_count"],
            event_count=row["event_count"],
        )
        for row in rows
    ]


def get_session(conn: sqlite3.Connection, session_id: int) -> SessionSummary | None:
    return next((s for s in list_sessions(conn) if s.id == session_id), None)


def load_frames(conn: sqlite3.Connection, session_id: int) -> list[FrameMetrics]:
    rows = conn.execute(
        "SELECT * FROM frames WHERE session_id = ? ORDER BY ts", (session_id,)
    ).fetchall()
    return [
        FrameMetrics(
            ts=row["ts"],
            dbfs=row["dbfs"],
            db_a=row["db_a"],
            db_c=row["db_c"],
            laf=row["db_a"],
            las=row["db_a"],
            leq_1s=row["leq_1s"] or 0.0,
            leq_10s=row["leq_10s"] or 0.0,
            leq_session=row["leq_10s"] or 0.0,
            lafmax=row["lafmax"] or 0.0,
            lcpeak=row["lcpeak"] or 0.0,
            spl=row["spl"],
            spl_a=row["db_spl_a"],
            spl_c=row["db_spl_c"],
        )
        for row in rows
    ]


def load_events(conn: sqlite3.Connection, session_id: int) -> list[NoiseEvent]:
    rows = conn.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY started_at", (session_id,)
    ).fetchall()
    return [
        NoiseEvent(
            started_at=row["started_at"],
            threshold=row["threshold"],
            peak=row["peak_db_a"],
            ended_at=row["ended_at"],
            audio_path=row["audio_path"],
        )
        for row in rows
    ]


def unfinished_sessions(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute("SELECT id FROM sessions WHERE ended_at IS NULL").fetchall()
    return [row["id"] for row in rows]
