"""分析器插件。导入本包即完成注册。"""

from . import device, music, noise, voice  # noqa: F401  （导入即注册）
from .base import Analyzer, available, create, register

__all__ = ["Analyzer", "available", "create", "register"]
