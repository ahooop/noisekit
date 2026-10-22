"""输出流编码兜底的行为测试。

这个函数救过四次火（CLI、纯度脚本、打包脚本、冻结后的 GUI），
所以行为必须固定下来：既不能因为编码再抛异常，也不能把 None 流留着。
"""

from __future__ import annotations

import io
import sys

from audio_core.console import ensure_utf8_console


class FakeStream(io.StringIO):
    encoding = "cp1252"

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict] = []

    def reconfigure(self, **kwargs) -> None:  # noqa: D401 - 模拟 TextIOWrapper
        self.calls.append(kwargs)


def test_reconfigures_non_utf8_streams(monkeypatch) -> None:
    out, err = FakeStream(), FakeStream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    ensure_utf8_console()

    assert out.calls and out.calls[0]["encoding"] == "utf-8"
    assert out.calls[0]["errors"] == "replace"
    assert err.calls


def test_utf8_stream_is_left_alone(monkeypatch) -> None:
    class Utf8Stream(FakeStream):
        encoding = "utf-8"

    out = Utf8Stream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", Utf8Stream())

    ensure_utf8_console()

    assert out.calls == []


def test_missing_streams_are_replaced(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    ensure_utf8_console()

    assert sys.stdout is not None
    assert sys.stderr is not None
    # 兜底流必须能装下中文，否则等于没修
    sys.stdout.write("中文\n")


def test_reconfigure_failure_does_not_raise(monkeypatch) -> None:
    class Broken(FakeStream):
        def reconfigure(self, **kwargs):
            raise OSError("不让改")

    monkeypatch.setattr(sys, "stdout", Broken())
    monkeypatch.setattr(sys, "stderr", Broken())

    ensure_utf8_console()  # 不抛异常即为通过
