"""桌面程序入口。

    python -m apps.desktop.main
    python -m apps.desktop.main --synthetic    # 没有麦克风时看界面
    python -m apps.desktop.main --selftest     # 打包冒烟：采 2 秒自动退出
"""

from __future__ import annotations

import argparse
import os
import sys

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
    return parser


def _run_selftest(app: QApplication, window: MainWindow) -> int:
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

    QTimer.singleShot(2500, app.quit)
    app.exec()

    worker = window._worker
    if worker is not None:
        worker.stop()
        worker.wait(3000)
    window.close()

    if not received:
        print("selftest: 失败，没有收到任何指标帧")
        return 1

    # 打包最常见的坑：分析链路正常，但 PortAudio 没打进去 → 一个设备都打不开。
    # 这里显式验证后端能加载，让 CI 在打包阶段就发现问题。
    from audio_core.capture.devices import backend_info, list_devices

    info = backend_info()
    if info.get("backend") == "unavailable":
        print("selftest: 失败，PortAudio 未加载（打包漏了 _sounddevice_data）")
        print(f"  诊断：{info}")
        return 1
    print(f"selftest: PortAudio {info['backend']}，输入设备 {len(list_devices())} 个")

    last = received[-1]
    print(f"selftest: ok，收到 {len(received)} 帧，最后一帧 dB(A)={last.db_a:.1f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_streams()
    args = build_parser().parse_args(argv)

    app = QApplication(sys.argv[:1] + ([] if argv is None else argv))
    app.setApplicationName("NoiseKit")
    app.setStyleSheet(STYLE_SHEET)

    window = MainWindow()
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
