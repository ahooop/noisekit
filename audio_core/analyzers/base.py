"""分析器插件协议与注册表。

M1 只实现 ``noise``。另外三个保留注册位，是为了让「加一个分析方向」变成
新增一个文件，而不是改动引擎——这也是这个项目将来能长大的前提。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

_REGISTRY: dict[str, type] = {}


@runtime_checkable
class Analyzer(Protocol):
    """分析器：吃音频块，吐一个扁平字典（可直接被存储/界面消费）。"""

    name: str
    display_name: str
    IMPLEMENTED: bool

    def process(self, block, timestamp: float) -> dict[str, Any]: ...


def register(cls: type) -> type:
    name = getattr(cls, "name", "")
    if not name:
        raise ValueError(f"{cls.__name__} 缺少 name 属性")
    if name in _REGISTRY:
        raise ValueError(f"分析器 {name!r} 已注册")
    _REGISTRY[name] = cls
    return cls


def available(include_unimplemented: bool = False) -> list[str]:
    if include_unimplemented:
        return sorted(_REGISTRY)
    return sorted(name for name, cls in _REGISTRY.items() if getattr(cls, "IMPLEMENTED", True))


def create(name: str, **kwargs) -> Analyzer:
    if name not in _REGISTRY:
        raise KeyError(f"未知分析器 {name!r}；可用：{', '.join(available(True))}")
    cls = _REGISTRY[name]
    if not getattr(cls, "IMPLEMENTED", True):
        raise NotImplementedError(f"分析器 {name!r} 尚未实现，计划见设计文档 §13")
    return cls(**kwargs)
