"""生成界面截图，用于 README 与人工检查渲染效果。

    python scripts/screenshot.py docs/screenshot.png

默认用 offscreen 平台，不需要真的显示窗口。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from apps.desktop.theme import STYLE_SHEET  # noqa: E402
from apps.desktop.windows import MainWindow  # noqa: E402

# offscreen 平台不会自动加载系统字体，不给它喂字体的话中文会变成方框
CANDIDATE_FONTS = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhl.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _load_fonts(app: QApplication) -> None:
    family = None
    for path in CANDIDATE_FONTS:
        if not Path(path).exists():
            continue
        font_id = QFontDatabase.addApplicationFont(path)
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families and family is None:
            family = families[0]
    if family:
        app.setFont(QFont(family, 9))


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshot.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLE_SHEET)
    _load_fonts(app)

    window = MainWindow()
    window.resize(980, 720)
    window.show()

    index = window.device_combo.findData("synthetic")
    if index >= 0:
        window.device_combo.setCurrentIndex(index)
    window.start()

    def capture() -> None:
        window.grab().save(str(out))
        window.stop()
        print(f"已保存 {out}")
        app.quit()

    QTimer.singleShot(4000, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
