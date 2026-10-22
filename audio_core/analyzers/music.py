"""音乐分析器占位。

计划在 v0.2 实现：BPM 估计、调性识别、音高追踪。
M1 只保留注册位，接口见 ``base.Analyzer``。
"""

from __future__ import annotations

from typing import Any

from .base import register


@register
class MusicAnalyzer:
    name = "music"
    display_name = "音乐分析"
    IMPLEMENTED = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("音乐分析器计划于 v0.2 实现，见设计文档 §13")

    def process(self, block, timestamp: float) -> dict[str, Any]:
        raise NotImplementedError
