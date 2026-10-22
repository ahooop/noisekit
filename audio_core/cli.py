"""命令行入口：不需要图形界面也能测。

    noisekit --source synthetic --duration 3
    noisekit --list-devices
    noisekit --doctor
    noisekit --calibrate 94.0
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time

import numpy as np

from . import __version__
from .analyzers import available as available_analyzers
from .analyzers.noise import NoiseAnalyzer
from .capture.devices import backend_info, find_device, list_devices, sounddevice_available
from .capture.source import SourceError
from .dsp.framing import mean_square
from .dsp.level import calibration_offset, mean_square_to_db


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noisekit",
        description="环境噪声监测：实时声级、Leq 与频谱（消费级麦克风，非计量认证）",
    )
    parser.add_argument("--version", action="version", version=f"noisekit {__version__}")
    parser.add_argument(
        "--source",
        choices=["device", "synthetic", "wav"],
        default="device",
        help="音频来源（默认 device）",
    )
    parser.add_argument("--device", help="设备序号或名称子串")
    parser.add_argument("--wav", help="--source wav 时的文件路径")
    parser.add_argument("--freq", type=float, default=1000.0, help="合成正弦频率（Hz）")
    parser.add_argument("--amplitude", type=float, default=1.0, help="合成信号幅度")
    parser.add_argument("--duration", type=float, help="运行秒数，缺省为一直运行")
    parser.add_argument(
        "--calibrate", type=float, metavar="REF_SPL", help="用参考声压级校准并退出"
    )
    parser.add_argument(
        "--calibration-offset", type=float, help="已知的校准偏移（dB），校准时无需再传入"
    )
    parser.add_argument("--list-devices", action="store_true", help="列出输入设备")
    parser.add_argument("--doctor", action="store_true", help="打印环境诊断信息")
    parser.add_argument("--analyzers", action="store_true", help="列出分析器")
    parser.add_argument(
        "--session-dir",
        metavar="DIR",
        help="把会话存进该目录：session.db + audio/ 留证录音 + report.html",
    )
    parser.add_argument(
        "--threshold", type=float, help="告警阈值（dB）；校准后默认 65，未校准默认 -30"
    )
    parser.add_argument("--trigger", type=float, default=3.0, help="超阈值持续秒数（默认 3）")
    parser.add_argument("--pre-roll", type=float, default=5.0, help="前置缓冲秒数（默认 5）")
    parser.add_argument("--post-roll", type=float, default=5.0, help="后置缓冲秒数（默认 5）")
    parser.add_argument("--cooldown", type=float, default=10.0, help="事件冷却秒数（默认 10）")
    return parser


def _create_source(args: argparse.Namespace):
    if args.source == "synthetic":
        from .capture.synthetic import SyntheticSource

        return SyntheticSource(
            kind="sine", freq=args.freq, amplitude=args.amplitude, duration=args.duration
        )
    if args.source == "wav":
        if not args.wav:
            raise SystemExit("--source wav 需要同时指定 --wav 文件路径")
        from .capture.wav_source import WavFileSource

        return WavFileSource(args.wav)
    from .capture.stream import SoundDeviceSource

    device = None
    if args.device:
        info = find_device(args.device)
        if info is None:
            raise SystemExit(f"找不到设备 {args.device!r}，用 --list-devices 查看可选值")
        device = info.index
    return SoundDeviceSource(device=device)


def _cmd_list_devices() -> int:
    if not sounddevice_available():
        print("音频后端不可用：pip install 'noisekit[audio]'")
        return 1
    devices = list_devices()
    if not devices:
        print("没有检测到任何输入设备。")
        return 1
    for dev in devices:
        print(dev)
    return 0


def _cmd_doctor() -> int:
    print(f"noisekit      {__version__}")
    print(f"python        {sys.version.split()[0]}")
    print(f"numpy         {np.__version__}")
    try:
        import scipy

        print(f"scipy         {scipy.__version__}")
    except Exception:
        print("scipy         (缺失)")
    try:
        import sounddevice

        print(f"sounddevice   {sounddevice.__version__}")
    except Exception as exc:
        print(f"sounddevice   (不可用: {exc})")
    for key, value in backend_info().items():
        print(f"{key:<13} {value}")
    print(f"输入设备数     {len(list_devices())}")
    return 0


def _cmd_analyzers() -> int:
    print("已实现：", ", ".join(available_analyzers()))
    print("预留：  ", ", ".join(available_analyzers(include_unimplemented=True)))
    return 0


def _format_frame(frame) -> str:
    suffix = "" if frame.spl_a is not None else " (相对)"
    return (
        f"L={frame.display_level():7.1f}{suffix}  "
        f"LAF={frame.laf:7.1f}  "
        f"Leq1s={frame.leq_1s:7.1f}  "
        f"Leq10s={frame.leq_10s:7.1f}  "
        f"峰={frame.lcpeak:7.1f}"
    )


def _device_label(source, args: argparse.Namespace) -> str:
    if args.source == "synthetic":
        return f"模拟信号 {args.freq:.0f} Hz"
    if args.source == "wav":
        return f"WAV {args.wav}"
    return f"设备 {getattr(source, 'device', '默认')}"


def _open_session(args: argparse.Namespace, source):
    if not args.session_dir:
        return None
    from .session import RecordingSession

    calibrated = args.calibration_offset is not None
    threshold = args.threshold
    if threshold is None:
        threshold = 65.0 if calibrated else -30.0
    return RecordingSession(
        root=args.session_dir,
        device_name=_device_label(source, args),
        sample_rate=source.sample_rate,
        calibration_offset=args.calibration_offset,
        threshold=threshold,
        trigger_seconds=args.trigger,
        pre_roll_seconds=args.pre_roll,
        post_roll_seconds=args.post_roll,
        cooldown_seconds=args.cooldown,
    )


def _report_notification(note) -> None:
    event = note.event
    if note.kind == "start":
        print(f"\n[事件] 超标开始 t={event.started_at:.1f}s 阈值={event.threshold:.0f}")
    else:
        path = event.audio_path or "未录音"
        print(
            f"\n[事件] 超标结束 持续 {event.duration:.1f}s 峰值 {event.peak:.1f} 录音={path}"
        )


def _close_session(session) -> None:
    try:
        summary = session.close()
        report = session.export_report()
        if summary is not None:
            state = "正常结束" if summary.finished else "未正常结束"
            print(f"会话 #{summary.id} 已保存（{state}）：{summary.frame_count} 帧指标")
        print(f"报告：{report}")
        print(f"录音目录：{session.audio_dir}")
    except Exception as exc:  # 收尾失败不该吞掉前面的数据
        print(f"会话收尾失败：{type(exc).__name__}: {exc}", file=sys.stderr)


def _calibrate(source, ref_spl: float) -> int:
    """用 2 秒平均值反算校准偏移。"""
    samples = np.empty(0, dtype=np.float32)
    need = int(2.0 * source.sample_rate)
    print(f"正在用 {ref_spl} dB 参考值校准，保持声源稳定 2 秒…")
    for block in source.blocks():
        samples = np.concatenate((samples, block))
        if samples.size >= need:
            break
    if samples.size == 0:
        print("没有收到音频，无法校准")
        return 1
    measured = mean_square_to_db(mean_square(samples))
    offset = calibration_offset(ref_spl, measured)
    print(f"实测 {measured:.1f} dBFS → 校准偏移 {offset:+.1f} dB")
    print("把该值作为 --calibration-offset 传入，或写入配置文件")
    return 0


def _ensure_utf8_console() -> None:
    """Windows 控制台默认可能是 GBK，中文提示会变乱码。"""
    stream = sys.stdout
    encoding = (getattr(stream, "encoding", "") or "").lower()
    if encoding and encoding.replace("-", "") != "utf8":
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_console()
    args = build_parser().parse_args(argv)

    if args.list_devices:
        return _cmd_list_devices()
    if args.doctor:
        return _cmd_doctor()
    if args.analyzers:
        return _cmd_analyzers()

    try:
        source = _create_source(args)
    except Exception as exc:
        print(f"无法启动采集：{exc}", file=sys.stderr)
        return 2

    if args.calibrate is not None:
        try:
            return _calibrate(source, args.calibrate)
        finally:
            source.close()

    analyzer = NoiseAnalyzer(source.sample_rate, calibration_offset=args.calibration_offset)
    session = _open_session(args, source)
    consumed = 0
    started = time.monotonic()
    last_print = 0.0
    frame = None
    try:
        for block in source.blocks():
            timestamp = consumed / source.sample_rate
            frame = analyzer.process_frame(block, timestamp)
            consumed += block.size
            if session is not None:
                for note in session.feed(block, frame):
                    _report_notification(note)
            now = time.monotonic()
            if now - last_print >= 0.25:
                last_print = now
                line = _format_frame(frame)
                if sys.stdout.isatty():
                    print("\r" + line, end="", flush=True)
                else:
                    print(line, flush=True)
            if args.duration and timestamp >= args.duration:
                break
    except KeyboardInterrupt:
        print()
    except SourceError as exc:
        print(f"\n采集中断：{exc}", file=sys.stderr)
        return 3
    finally:
        source.close()
        if session is not None:
            _close_session(session)
    if sys.stdout.isatty():
        print()
    elapsed = time.monotonic() - started
    if frame is None:
        print("没有收到任何音频")
        return 1
    analyzed = consumed / source.sample_rate
    print(f"分析 {analyzed:.1f} 秒音频（耗时 {elapsed:.1f} 秒），Leq={frame.leq_session:.1f}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
