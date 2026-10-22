"""SQLite 落盘与读取的测试。"""

from __future__ import annotations

from datetime import datetime

import pytest

from audio_core.events.detector import NoiseEvent
from audio_core.metrics.meter import FrameMetrics
from audio_core.storage.query import (
    list_sessions,
    load_events,
    load_frames,
    unfinished_sessions,
)
from audio_core.storage.schema import connect
from audio_core.storage.writer import SessionWriter


def make_frame(ts: float, level: float = -30.0) -> FrameMetrics:
    return FrameMetrics(
        ts=ts,
        dbfs=level,
        db_a=level,
        db_c=level,
        laf=level,
        las=level,
        leq_1s=level,
        leq_10s=level,
        leq_session=level,
        lafmax=level,
        lcpeak=level,
        spl=None,
        spl_a=None,
        spl_c=None,
    )


def test_frames_roundtrip(tmp_path) -> None:
    db = tmp_path / "session.db"
    with SessionWriter(db) as writer:
        session_id = writer.start_session("测试设备", 48000)
        for index in range(250):
            writer.add_frame(make_frame(index * 0.1, -40.0 + index * 0.01))
        writer.flush()
        assert writer.frames_written == 250

    conn = connect(db)
    frames = load_frames(conn, session_id)
    assert len(frames) == 250
    assert frames[0].ts == pytest.approx(0.0)
    assert frames[-1].ts == pytest.approx(24.9, abs=0.05)


def test_events_roundtrip(tmp_path) -> None:
    db = tmp_path / "session.db"
    writer = SessionWriter(db)
    session_id = writer.start_session("mic", 48000, calibration_offset=124.0)
    event = NoiseEvent(started_at=3.0, threshold=65.0, peak=81.5, ended_at=9.0)
    event.audio_path = str(tmp_path / "event_1.wav")
    writer.add_event(event, pre_roll=5.0, post_roll=5.0)
    writer.end_session()
    writer.close()

    conn = connect(db)
    events = load_events(conn, session_id)
    assert len(events) == 1
    assert events[0].peak == pytest.approx(81.5)
    assert events[0].duration == pytest.approx(6.0)
    assert events[0].audio_path.endswith("event_1.wav")


def test_session_metadata_and_finish_flag(tmp_path) -> None:
    db = tmp_path / "session.db"
    writer = SessionWriter(db)
    session_id = writer.start_session(
        "mic", 44100, calibration_offset=None, label="楼上装修", started_at=datetime(2026, 10, 22, 23, 30)
    )
    writer.end_session()
    writer.close()

    conn = connect(db)
    sessions = list_sessions(conn)
    assert len(sessions) == 1
    summary = sessions[0]
    assert summary.id == session_id
    assert summary.finished
    assert summary.label == "楼上装修"
    assert summary.sample_rate == 44100
    assert "2026-10-22T23:30" in summary.started_at


def test_unfinished_session_is_detected(tmp_path) -> None:
    """模拟崩溃：只开了会话，没写 ended_at。"""
    db = tmp_path / "session.db"
    writer = SessionWriter(db)
    session_id = writer.start_session("mic", 48000)
    for index in range(20):
        writer.add_frame(make_frame(index * 0.1))
    writer.close()  # 直接关，不调用 end_session

    conn = connect(db)
    assert unfinished_sessions(conn) == [session_id]
    summary = list_sessions(conn)[0]
    assert not summary.finished
    # 数据仍然可读——这是「断电也不丢已有数据」的保证
    assert summary.frame_count == 20
    assert len(load_frames(conn, session_id)) == 20


def test_writer_requires_session(tmp_path) -> None:
    writer = SessionWriter(tmp_path / "x.db")
    with pytest.raises(RuntimeError):
        writer.add_frame(make_frame(0.0))
    writer.close()


def test_multiple_sessions_are_separated(tmp_path) -> None:
    db = tmp_path / "session.db"
    writer = SessionWriter(db)
    first = writer.start_session("mic-1", 48000)
    writer.add_frame(make_frame(0.0))
    writer.end_session()
    writer.close()

    writer = SessionWriter(db)
    second = writer.start_session("mic-2", 48000)
    writer.add_frame(make_frame(0.0))
    writer.add_frame(make_frame(0.1))
    writer.end_session()
    writer.close()

    conn = connect(db)
    assert first != second
    assert len(load_frames(conn, first)) == 1
    assert len(load_frames(conn, second)) == 2
