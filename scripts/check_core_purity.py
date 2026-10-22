"""架构约束：audio_core 不得依赖任何 GUI 框架。

引擎要能被别人 pip 装进无头环境复用，这条约束一旦破掉就回不去了。
CI 与本地测试都会跑它。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from audio_core.console import ensure_utf8_console  # noqa: E402

FORBIDDEN = ("PySide6", "PyQt5", "PyQt6", "tkinter", "app.desktop")
ROOT = ROOT_DIR / "audio_core"


def find_violations() -> list[str]:
    problems: list[str] = []
    for path in ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for banned in FORBIDDEN:
                if banned in stripped:
                    problems.append(f"{path.relative_to(ROOT.parent)}:{lineno}: {stripped}")
    return problems


def main() -> int:
    ensure_utf8_console()
    problems = find_violations()
    if problems:
        print("audio_core 中出现了禁止的 GUI 依赖：")
        for item in problems:
            print("  " + item)
        return 1
    print("audio_core 纯度检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
