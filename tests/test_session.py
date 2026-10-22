"""端到端：一段「安静 → 吵闹 → 安静」的录音，应产出数据库、留证音频和报告。

这是 M1.2 的验收测试——不看单个函数，只看最终用户拿到什么。
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.io import wavfile

from audio_core.analyzers.noise import NoiseAnalyzer
from audio_core.capture.wav_source import WavFileSource
from audio_core.session import RecordingSession
from audio_core.storage.query import list_sessions, load_events, load_frames
from audio_core.storage.schema import connect

FS = 48000


def _tone(seconds: float, amplitude: float, freq: float = 1000.0) -> np.ndarray:
    t = np.arange(int(seconds * FS)) / FS
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def build_sample(path) -> None:
    """4 秒安静（约 −57 dB）+ 8 秒吵闹（约 −9 dB）+ 4 秒安静。"""
    quiet = _tone(4.0, 0.002)
    loud = _tone(8.0, 0.5)
    tail = _tone(4.0, 0.002)
    signal = np.concatenate([quiet, loud, tail])
    wavfile.write(path, FS, (np.clip(signal, -1, 1) * 32767).astype(np.int16))


def run_session(tmp_path) -> RecordingSession:
    wav = tmp_path / "sample.wav"
    build_sample(wav)

    session = RecordingSession(
        root=tmp_path / "session",
        device_name="测试信号",
        sample_rate=FS,
        calibration_offset=None,
        threshold=-20.0,  # 相对 dB
        trigger_seconds=1.0,
        pre_roll_seconds=2.0,
        post_roll_seconds=1.0,
        cooldown_seconds=1.0,
    )
    analyzer = NoiseAnalyzer(FS)
    source = WavFileSource(wav)

    consumed = 0
    for block in source.blocks():
        frame = analyzer.process_frame(block, consumed / FS)
        consumed += block.size
        session.feed(block, frame)
    session.close()
    return session


def test_session_produces_event_audio_and_report(tmp_path) -> None:
    session = run_session(tmp_path)

    assert len(session.events) == 1
    event = session.events[0]
    assert event.peak > -20.0
    assert event.duration > 5.0

    audio = [p for p in session.audio_dir.glob("*.wav")]
    assert len(audio) == 1
    rate, data = wavfile.read(audio[0])
    assert rate == FS
    # 2 秒前置 + 噪音段 + 1 秒后置，音频时长应明显长于事件本身
    assert data.size / FS > event.duration
    assert np.max(np.abs(data.astype(np.float32) / 32768.0)) > 0.1


def test_session_database_is_consistent(tmp_path) -> None:
    session = run_session(tmp_path)

    conn = connect(session.db_path)
    summaries = list_sessions(conn)
    assert len(summaries) == 1
    assert summaries[0].finished
    assert summaries[0].event_count == 1

    frames = load_frames(conn, session.session_id)
    assert len(frames) > 100
    stamps = [f.ts for f in frames]
    assert stamps == sorted(stamps)

    events = load_events(conn, session.session_id)
    assert len(events) == 1
    assert events[0].audio_path is not None


def test_session_report_is_self_contained(tmp_path) -> None:
    session = run_session(tmp_path)
    report = session.export_report()
    text = report.read_text(encoding="utf-8")

    assert report.exists()
    assert "<svg" in text
    assert "计量认证" in text
    assert "不得用于执法取证" in text
    assert "超标事件" in text
    # 录音文件名要出现在报告里，不然「留证」是断的
    assert [p.name for p in session.audio_dir.glob("*.wav")][0] in text


def test_session_csv_export(tmp_path) -> None:
    session = run_session(tmp_path)
    path = session.export_csv()
    lines = path.read_text(encoding="utf-8-sig").strip().splitlines()
    assert lines[0].startswith("ts,")
    assert len(lines) > 100


def test_session_close_is_idempotent(tmp_path) -> None:
    session = run_session(tmp_path)
    assert session.close() is None


def test_feed_after_close_is_rejected(tmp_path) -> None:
    session = run_session(tmp_path)
    with pytest.raises(RuntimeError):
        session.feed(np.zeros(480, dtype=np.float32), None)
