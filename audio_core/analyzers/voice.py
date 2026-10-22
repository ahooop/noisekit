"""语音分析器占位。

计划在 v0.3 实现：端点检测（VAD）、静音裁剪、可选转写。
注意：这一路需要外部模型，与 M1 的「纯确定性 DSP」定位不同，需单独评估体积与算力。
"""

from __future__ import annotations

from typing import Any

from .base import register


@register
class VoiceAnalyzer:
    name = "voice"
    display_name = "语音分析"
    IMPLEMENTED = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("语音分析器计划于 v0.3 实现，见设计文档 §13")

    def process(self, block, timestamp: float) -> dict[str, Any]:
        raise NotImplementedError
