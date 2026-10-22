"""单页 HTML 报告。

原则：**一个文件、零外部依赖**。发给物业、房东、朋友，双击就能看，
不需要联网、不需要装东西、图片和样式全在文件里。

曲线用内联 SVG 画，不引任何图表库。
"""

from __future__ import annotations

import html
from pathlib import Path

from ..events.detector import NoiseEvent
from ..metrics.meter import FrameMetrics
from ..storage.query import SessionSummary

DISCLAIMER = (
    "本报告由 NoiseKit 生成。测量使用消费级麦克风配合软件计算，"
    "不是计量认证仪器（不符合 IEC 61672 / GB/T 3785 对 1 级或 2 级声级计的要求）。"
    "数据仅供个人参考、趋势对比与过程记录，不得用于执法取证、工程验收或法定检测。"
)

MAX_POINTS = 1200
SVG_WIDTH = 960
SVG_HEIGHT = 260


def _display_level(frame: FrameMetrics) -> float:
    return frame.spl_a if frame.spl_a is not None else frame.db_a


def _downsample(frames: list[FrameMetrics], limit: int = MAX_POINTS) -> list[FrameMetrics]:
    if len(frames) <= limit:
        return frames
    step = len(frames) / limit
    return [frames[int(i * step)] for i in range(limit)]


def _curve_svg(
    frames: list[FrameMetrics],
    lo: float,
    hi: float,
    threshold: float | None,
) -> str:
    if len(frames) < 2:
        return '<p class="empty">数据点不足，无法绘制曲线。</p>'

    points = _downsample(frames)
    t0, t1 = points[0].ts, points[-1].ts
    span = max(t1 - t0, 1e-6)
    pad_left, pad_right, pad_top, pad_bottom = 48, 12, 12, 26
    plot_w = SVG_WIDTH - pad_left - pad_right
    plot_h = SVG_HEIGHT - pad_top - pad_bottom

    def x(ts: float) -> float:
        return pad_left + plot_w * (ts - t0) / span

    def y(value: float) -> float:
        ratio = (min(max(value, lo), hi) - lo) / max(hi - lo, 1e-6)
        return pad_top + plot_h * (1.0 - ratio)

    polyline = " ".join(f"{x(f.ts):.1f},{y(_display_level(f)):.1f}" for f in points)

    grid = []
    step = 10 if hi - lo >= 40 else 5
    value = lo
    while value <= hi + 1e-6:
        yy = y(value)
        grid.append(
            f'<line x1="{pad_left}" y1="{yy:.1f}" x2="{SVG_WIDTH - pad_right}" y2="{yy:.1f}" '
            f'stroke="#e6e9ef" stroke-width="1"/>'
            f'<text x="{pad_left - 8}" y="{yy + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#8b95a5">{int(value)}</text>'
        )
        value += step

    threshold_line = ""
    if threshold is not None and lo <= threshold <= hi:
        ty = y(threshold)
        threshold_line = (
            f'<line x1="{pad_left}" y1="{ty:.1f}" x2="{SVG_WIDTH - pad_right}" y2="{ty:.1f}" '
            f'stroke="#e53935" stroke-width="1" stroke-dasharray="6 4"/>'
            f'<text x="{SVG_WIDTH - pad_right}" y="{ty - 5:.1f}" text-anchor="end" '
            f'font-size="11" fill="#e53935">阈值 {threshold:.0f}</text>'
        )

    ticks = []
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        ts = t0 + span * fraction
        ticks.append(
            f'<text x="{x(ts):.1f}" y="{SVG_HEIGHT - 8}" text-anchor="middle" '
            f'font-size="11" fill="#8b95a5">{_format_offset(ts)}</text>'
        )

    return (
        f'<svg viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" width="100%" '
        f'role="img" aria-label="声级随时间变化曲线">'
        + "".join(grid)
        + threshold_line
        + f'<polyline fill="none" stroke="#1e88e5" stroke-width="1.6" points="{polyline}"/>'
        + "".join(ticks)
        + "</svg>"
    )


def _format_offset(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分 {secs} 秒"
    if minutes:
        return f"{minutes} 分 {secs} 秒"
    return f"{secs} 秒"


def write_report(
    path: str | Path,
    session: SessionSummary,
    frames: list[FrameMetrics],
    events: list[NoiseEvent],
    title: str = "环境噪声测量报告",
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    calibrated = session.calibration_offset is not None
    unit = "dB(A) SPL" if calibrated else "dB(A)（相对值，未校准）"

    levels = [_display_level(f) for f in frames]
    if levels:
        peak = max(levels)
        average = sum(levels) / len(levels)
        lo = min(levels) - 5
        hi = max(levels) + 5
    else:
        peak = average = 0.0
        lo, hi = (-90.0, 0.0) if not calibrated else (30.0, 120.0)
    lo = min(lo, -90) if not calibrated else max(lo, 10)
    threshold = events[0].threshold if events else None
    if threshold is not None:
        lo = min(lo, threshold - 10)
        hi = max(hi, threshold + 10)

    duration = frames[-1].ts - frames[0].ts if frames else 0.0
    leq_session = frames[-1].leq_session if frames else 0.0

    rows = []
    for index, event in enumerate(events, start=1):
        audio = ""
        if event.audio_path:
            name = Path(event.audio_path).name
            audio = f'<a href="{html.escape(name)}">{html.escape(name)}</a>'
        else:
            audio = '<span class="muted">未保存</span>'
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{_format_offset(event.started_at)}</td>"
            f"<td>{event.duration:.1f} 秒</td>"
            f"<td>{event.peak:.1f}</td>"
            f"<td>{audio}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="5" class="muted">本次会话没有超标事件</td></tr>')

    updated_note = "" if session.finished else (
        '<p class="warn">⚠ 本次会话未正常结束（程序被关闭或崩溃），已保存的数据仍然有效。</p>'
    )

    body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · {html.escape(session.started_at)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; padding: 32px; font: 15px/1.7 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         color: #1c2330; background: #f6f7f9; }}
  .page {{ max-width: 1000px; margin: 0 auto; background: #fff; padding: 32px 36px;
           border-radius: 10px; box-shadow: 0 1px 3px rgba(16,24,40,.08); }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 16px; margin: 28px 0 10px; }}
  .meta {{ color: #6b7688; font-size: 13px; }}
  .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0 8px; }}
  .card {{ background: #f6f7f9; border-radius: 8px; padding: 12px 14px; }}
  .card b {{ display: block; font-size: 20px; margin-top: 2px; }}
  .card span {{ color: #6b7688; font-size: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #eceff3; }}
  th {{ color: #6b7688; font-weight: 600; font-size: 12px; }}
  .muted {{ color: #98a2b3; }}
  .warn {{ background: #fff6e5; border-left: 3px solid #f0a020; padding: 10px 14px; border-radius: 4px; }}
  footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #eceff3;
            color: #8b95a5; font-size: 12px; }}
</style>
</head>
<body>
<div class="page">
  <h1>{html.escape(title)}</h1>
  <p class="meta">
    开始 {html.escape(session.started_at)}
    {("· 结束 " + html.escape(session.ended_at)) if session.ended_at else ""}
    · 设备 {html.escape(session.device_name or "未知")}
    · 采样率 {session.sample_rate} Hz
    · 校准 {(f"偏移 {session.calibration_offset:+.1f} dB") if calibrated else "未校准"}
  </p>
  {updated_note}

  <div class="cards">
    <div class="card"><span>时长</span><b>{_format_duration(duration)}</b></div>
    <div class="card"><span>Leq（全程）</span><b>{leq_session:.1f}</b><span>{html.escape(unit)}</span></div>
    <div class="card"><span>最大</span><b>{peak:.1f}</b><span>{html.escape(unit)}</span></div>
    <div class="card"><span>超标事件</span><b>{len(events)}</b><span>次</span></div>
  </div>

  <h2>声级曲线</h2>
  {_curve_svg(frames, lo, hi, threshold)}
  <p class="meta">横轴为会话内时间（分:秒），纵轴单位 {html.escape(unit)}；平均读数 {average:.1f}。</p>

  <h2>超标事件</h2>
  <table>
    <thead><tr><th>#</th><th>开始</th><th>持续</th><th>峰值</th><th>录音</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>

  <footer>{html.escape(DISCLAIMER)}</footer>
</div>
</body>
</html>
"""
    target.write_text(body, encoding="utf-8")
    return target
