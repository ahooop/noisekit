"""控制台编码兜底。

Windows 控制台的默认编码可能是 cp1252 / cp936，`print` 一句中文就会抛
``UnicodeEncodeError`` 把脚本打死。同一个 bug 在这个仓库里已经出现过三次
（CLI、纯度检查、打包脚本），所以收成一个函数，别再复制第四份。
"""

from __future__ import annotations

import contextlib
import sys


def ensure_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None:  # --windowed 打包后 stdout 可能就是 None
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower()
        if encoding and encoding.replace("-", "") != "utf8":
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8", errors="replace")
