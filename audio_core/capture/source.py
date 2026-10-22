"""音频来源协议。

采集层与上层之间唯一的契约。真实设备、合成信号、WAV 回放都实现它，
于是 ``audio_core`` 的全部逻辑在没有麦克风的环境（CI）里也能被测到。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class AudioSource(Protocol):
    """单声道浮点音频块来源，样本范围 [-1, 1]。"""

    sample_rate: int
    channels: int
    block_frames: int

    def blocks(self) -> Iterator[np.ndarray]:
        """按 ``block_frames`` 长度持续产出块；结束时生成器返回。"""
        ...

    def close(self) -> None:
        """释放底层资源，幂等。"""
        ...


class SourceError(RuntimeError):
    """音频来源不可用（设备被占用、文件损坏等）。"""
