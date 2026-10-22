"""桌面程序入口。

    python -m apps.desktop.main
    python -m apps.desktop.main --synthetic    # 没有麦克风时看界面
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from apps.desktop.theme import STYLE_SHEET
from apps.desktop.windows import MainWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noisekit-ui", description="NoiseKit 桌面界面")
    parser.add_argument("--synthetic", action="store_true", help="启动后直接使用模拟信号")
    parser.add_argument("--device", type=int, help="要预选的设备序号")
    parser.add_argument("--calibration-offset", type=float, help="预填校准偏移（dB）")
    return parser


def main(argv: list[str] | None = None) -> int:
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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
