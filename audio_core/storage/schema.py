"""SQLite 表结构。

设计文档 §6 的落地。两处刻意的选择：

* ``frames`` 存 10 Hz 原始指标，而不是按分钟聚合——事后想换个平滑窗口重算，
  原始数据还在；一小时约 3.6 万行，SQLite 毫无压力。
* 会话是否正常结束**不额外存字段**，用 ``ended_at IS NULL`` 表达。
  能被推导出来的状态就不要存第二份，否则迟早不一致。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        device_name TEXT,
        sample_rate INTEGER NOT NULL,
        calibration_offset REAL,
        label TEXT,
        notes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS frames (
        id INTEGER PRIMARY KEY,
        session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        ts REAL NOT NULL,
        dbfs REAL NOT NULL,
        db_a REAL NOT NULL,
        db_c REAL NOT NULL,
        spl REAL,
        db_spl_a REAL,
        db_spl_c REAL,
        leq_1s REAL,
        leq_10s REAL,
        lafmax REAL,
        lcpeak REAL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_frames_session_ts ON frames(session_id, ts)",
    """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY,
        session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        started_at REAL NOT NULL,
        ended_at REAL,
        threshold REAL NOT NULL,
        peak_db_a REAL NOT NULL,
        audio_path TEXT,
        pre_roll REAL NOT NULL,
        post_roll REAL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)",
)


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA:
        conn.execute(statement)
    conn.commit()
