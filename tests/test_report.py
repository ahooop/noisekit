"""CSV 与 HTML 报告导出的测试。"""

from __future__ import annotations

import numpy as np

from audio_core.events.detector import NoiseEvent
from audio_core.metrics.meter import FrameMetrics
from audio_core.report.csv_export import write_csv
from audio_core.report.html_export import DISCLAIMER, write_report
from audio_core.storage.query import SessionSummary


def frames(count: int = 200, base: float = -45.0) -> list[FrameMetrics]:
    rng = np.random.default_rng(0)
    result = []
    for index in range(count):
        level = base + 6 * np.sin(index / 12) + float(rng.normal(0, 0.3))
        result.append(
            FrameMetrics(
                ts=index * 0.1,
                dbfs=level,
                db_a=level,
                db_c=level,
                laf=level,
                las=level,
                leq_1s=level,
                leq_10s=level,
                leq_session=base,
                lafmax=level + 3,
                lcpeak=level + 6,
            )
        )
    return result


def session(calibrated: bool = False, finished: bool = True) -> SessionSummary:
    return SessionSummary(
        id=1,
        started_at="2026-10-22T23:30:00",
        ended_at="2026-10-22T23:35:00" if finished else None,
        device_name="Realtek 麦克风",
        sample_rate=48000,
        calibration_offset=124.0 if calibrated else None,
        label="楼上装修",
        frame_count=200,
        event_count=1,
    )


def test_csv_has_header_and_rows(tmp_path) -> None:
    path = write_csv(tmp_path / "metrics.csv", frames(10))
    lines = path.read_text(encoding="utf-8-sig").strip().splitlines()
    assert lines[0].startswith("ts,dbfs,db_a")
    assert len(lines) == 11


def test_report_contains_curve_and_disclaimer(tmp_path) -> None:
    path = write_report(tmp_path / "report.html", session(), frames(), [])
    text = path.read_text(encoding="utf-8")
    assert "<svg" in text
    assert "<polyline" in text
    assert DISCLAIMER in text
    assert "没有超标事件" in text


def test_report_lists_events_with_audio(tmp_path) -> None:
    (tmp_path / "event_1.wav").write_bytes(b"RIFF")
    event = NoiseEvent(started_at=30.0, threshold=65.0, peak=78.5, ended_at=42.0)
    event.audio_path = str(tmp_path / "event_1.wav")

    path = write_report(tmp_path / "report.html", session(calibrated=True), frames(), [event])
    text = path.read_text(encoding="utf-8")
    assert "event_1.wav" in text
    assert "78.5" in text
    assert "00:30" in text
    assert "dB(A) SPL" in text


def test_report_marks_unfinished_session(tmp_path) -> None:
    path = write_report(tmp_path / "report.html", session(finished=False), frames(), [])
    text = path.read_text(encoding="utf-8")
    assert "未正常结束" in text


def test_report_uses_relative_label_when_uncalibrated(tmp_path) -> None:
    path = write_report(tmp_path / "report.html", session(calibrated=False), frames(), [])
    assert "相对值，未校准" in path.read_text(encoding="utf-8")


def test_report_handles_empty_frames(tmp_path) -> None:
    path = write_report(tmp_path / "report.html", session(), [], [])
    text = path.read_text(encoding="utf-8")
    assert "数据点不足" in text


def test_report_escapes_html(tmp_path) -> None:
    bad = SessionSummary(
        id=2,
        started_at="<script>alert(1)</script>",
        ended_at=None,
        device_name="<b>device</b>",
        sample_rate=48000,
        calibration_offset=None,
        label=None,
        frame_count=0,
        event_count=0,
    )
    path = write_report(tmp_path / "report.html", bad, [], [])
    text = path.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_report_curve_stays_inside_canvas(tmp_path) -> None:
    path = write_report(tmp_path / "report.html", session(), frames(), [])
    text = path.read_text(encoding="utf-8")
    start = text.index("<polyline")
    end = text.index("/>", start)
    points = text[start:end].split('points="')[1].strip('"').split()
    assert points
    for point in points[:50]:
        x_str, y_str = point.split(",")
        assert 0 <= float(x_str) <= 960
        assert 0 <= float(y_str) <= 260
