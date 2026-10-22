"""控制台/输出流编码兜底。

这个坑在仓库里已经出现过四次：CLI、纯度检查、打包脚本、以及**冻结后的 GUI**。
表现都是同一句话：Windows 默认编码（cp1252 / cp936）装不下中文，
``print`` 抛 ``UnicodeEncodeError``。

冻结后尤其阴险：``--windowed`` 打包的程序一旦抛未处理异常，PyInstaller 会弹出
一个错误对话框，于是进程既不退出也不输出——在 CI 里看起来就是「卡死」。

所以：任何会 ``print`` 中文的入口，第一件事都调它。
"""

from __future__ import annotations

import contextlib
import os
import sys


def ensure_utf8_console() -> None:
    """把 stdout / stderr 调整成「能装下中文、且永不因编码抛异常」的状态。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            # --windowed 打包后没有控制台，给一个黑洞，避免 print 直接崩
            try:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115
            except OSError:
                continue
            continue

        encoding = (getattr(stream, "encoding", "") or "").lower()
        if encoding.replace("-", "") == "utf8":
            continue
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")
