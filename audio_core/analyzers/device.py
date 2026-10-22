"""设备实测分析器占位。

计划在 v0.2+ 实现：频响曲线（扫频/白噪）、底噪、总谐波失真、左右声道一致性。
这一路对「校准信号源」有硬性要求，不能只靠软件。
"""

from __future__ import annotations

from typing import Any

from .base import register


@register
class DeviceAnalyzer:
    name = "device"
    display_name = "设备实测"
    IMPLEMENTED = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("设备实测分析器尚未排期，见设计文档 §1.3")

    def process(self, block, timestamp: float) -> dict[str, Any]:
        raise NotImplementedError
