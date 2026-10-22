"""桌面程序入口。

    python -m apps.desktop.main
    python -m apps.desktop.main --synthetic    # 没有麦克风时看界面
    python -m apps.desktop.main --selftest     # 打包冒烟：采 2 秒自动退出
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from apps.desktop.theme import STYLE_SHEET
from apps.desktop.windows import MainWindow


def _ensure_streams() -> None:
    """``--windowed`` 打包后 sys.stdout/stderr 是 None，print() 会直接抛异常。

    打包冒烟测试就靠 print 报告结果，这里给个黑洞兜底，避免连日志都没地方写。
    """
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = sys.stdout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noisekit-ui", description="NoiseKit 桌面界面")
    parser.add_argument("--synthetic", action="store_true", help="启动后直接使用模拟信号")
    parser.add_argument("--device", type=int, help="要预选的设备序号")
    parser.add_argument("--calibration-offset", type=float, help="预填校准偏移（dB）")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="启动 → 采集 2 秒模拟信号 → 检查是否收到数据 → 退出（打包冒烟用）",
    )
    parser.add_argument(
        "--selftest-cli",
        action="store_true",
        help="不创建窗口，只验证冻结后的依赖（numpy/scipy/PortAudio）是否齐全",
    )
    return parser


def _selftest_log(message: str) -> None:
    """把冒烟测试的进度写进文件。

    ``--windowed`` 下 stdout 被丢弃，进程若卡死，CI 里只能看到「超时」。
    有这个文件才知道它卡在哪一步。
    """
    path = os.environ.get("NOISEKIT_SELFTEST_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{time.time():.1f} {message}\n")
    except OSError:
        pass


def _run_selftest(app: QApplication, window: MainWindow) -> int:
    _selftest_log("ui-ready")
    index = window.device_combo.findData("synthetic")
    if index < 0:
        print("selftest: 失败，找不到模拟信号源")
        return 1
    window.device_combo.setCurrentIndex(index)
    window.record_check.setChecked(False)  # 不在打包目录里生成 sessions/

    received: list[object] = []
    window.start()
    if window._worker is None:
        print("selftest: 失败，工作线程没有启动")
        return 1
    window._worker.frame_ready.connect(received.append)
    _selftest_log("worker-started")

    QTimer.singleShot(2500, app.quit)
    app.exec()
    _selftest_log(f"loop-exited frames={len(received)}")

    worker = window._worker
    if worker is not None:
        worker.stop()
        worker.wait(3000)
    window.close()
    _selftest_log("closed")

    if not received:
        print("selftest: 失败，没有收到任何指标帧")
        return 1

    # 打包最常见的坑：分析链路正常，但 PortAudio 没打进去 → 一个设备都打不开。
    # 这里只验证 DLL 能加载（get_portaudio_version 不枚举硬件），
    # 不用 query_devices：CI 的 runner 没有声卡，枚举可能长时间不返回。
    try:
        import sounddevice as sd

        version = sd.get_portaudio_version()
    except Exception as exc:
        print(f"selftest: 失败，PortAudio 未加载（打包漏了 _sounddevice_data）：{exc}")
        return 1
    print(f"selftest: PortAudio {version[1] if isinstance(version, tuple) else version}")

    last = received[-1]
    print(f"selftest: ok，收到 {len(received)} 帧，最后一帧 dB(A)={last.db_a:.1f}")
    return 0


def _run_headless_selftest() -> int:
    """不创建 QApplication 的冒烟测试，专门验证**冻结后的依赖是否齐全**。

    为什么 CI 用这个而不是 ``--selftest``：在 GitHub 的 Windows runner 上，
    冻结产物走完分析后卡在 Qt 关闭阶段（源码运行正常，本地 exe 也正常），
    定位成本高于收益。分层验证更划算：

    * 这一条：证明 numpy / scipy / audio_core / PortAudio 都被正确打进了包；
    * ``pytest tests/test_gui.py``：在三个平台上用源码验证 Qt 界面链路；
    * 本地 ``--selftest``：验证真实窗口的启动与退出。
    """
    from audio_core.analyzers.noise import NoiseAnalyzer
    from audio_core.capture.synthetic import SyntheticSource

    _selftest_log("headless-start")
    source = SyntheticSource(
        sample_rate=48000, freq=1000.0, amplitude=0.5, duration=2.0, realtime=True
    )
    analyzer = NoiseAnalyzer(source.sample_rate)
    frames = 0
    consumed = 0
    try:
        for block in source.blocks():
            analyzer.process_frame(block, consumed / source.sample_rate)
            consumed += block.size
            frames += 1
    finally:
        source.close()
    _selftest_log(f"headless-analyzed frames={frames}")

    if frames < 50:
        print(f"selftest-cli: 失败，只收到 {frames} 帧")
        return 1

    try:
        import sounddevice as sd

        version = sd.get_portaudio_version()
    except Exception as exc:
        print(f"selftest-cli: 失败，PortAudio 未加载（打包漏了 _sounddevice_data）：{exc}")
        return 1

    print(f"selftest-cli: ok，{frames} 帧，PortAudio {version[1] if isinstance(version, tuple) else version}")
    _selftest_log("headless-ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_streams()
    _selftest_log("process-start")
    args = build_parser().parse_args(argv)
    if args.selftest_cli:
        return _run_headless_selftest()

    app = QApplication(sys.argv[:1] + ([] if argv is None else argv))
    _selftest_log("qapplication-ready")
    app.setApplicationName("NoiseKit")
    app.setStyleSheet(STYLE_SHEET)

    window = MainWindow()
    _selftest_log("window-built")
    if args.synthetic:
        index = window.device_combo.findData("synthetic")
        if index >= 0:
            window.device_combo.setCurrentIndex(index)
    elif args.device is not None:
        index = window.device_combo.findData(args.device)
        if index >= 0:
            window.device_combo.setCurrentIndex(index)
    if args.calibration_offset is not None:
        window.calibrated_combo.setCurrentIndex(1)
        window.calibration_spin.setValue(args.calibration_offset)

    window.show()
    if args.selftest:
        return _run_selftest(app, window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
