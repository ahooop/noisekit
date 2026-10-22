"""环境噪声分析器（M1 唯一实现）。"""

from __future__ import annotations

from typing import Any

from ..metrics.meter import SoundLevelMeter
from .base import register


@register
class NoiseAnalyzer:
    name = "noise"
    display_name = "环境噪声"
    IMPLEMENTED = True

    def __init__(self, sample_rate: int, calibration_offset: float | None = None) -> None:
        self.meter = SoundLevelMeter(sample_rate, calibration_offset=calibration_offset)

    @property
    def block_frames(self) -> int:
        return self.meter.block_frames

    def process_frame(self, block, timestamp: float):
        """返回完整的 ``FrameMetrics``，供界面直接使用。"""
        return self.meter.process(block, timestamp)

    def process(self, block, timestamp: float) -> dict[str, Any]:
        """插件契约：扁平字典。"""
        return self.meter.process(block, timestamp).as_dict()

    def reset(self) -> None:
        self.meter.reset()
