"""用户配置：记住上次用的设备、校准值、阈值。

放在系统标准位置，不往仓库目录里写——用户下载 exe 双击运行时，
工作目录可能是任意地方，甚至是只读的 Program Files。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import get_args, get_type_hints

APP_NAME = "NoiseKit"
CONFIG_NAME = "config.json"


def config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / APP_NAME


def config_path() -> Path:
    return config_dir() / CONFIG_NAME


@dataclass
class AppConfig:
    device_index: int | None = None
    calibrated: bool = False
    calibration_offset: float = 0.0
    threshold: float = -30.0
    output_dir: str | None = None
    window_width: int = 1147
    window_height: int = 839

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> AppConfig:
        """只认识自己知道的字段；类型不对就用默认值，绝不因为配置坏了启动不了。"""
        defaults = cls()
        hints = get_type_hints(cls)
        values = {}
        for field in fields(cls):
            default = getattr(defaults, field.name)
            raw = data.get(field.name, default)
            values[field.name] = _coerce(raw, hints.get(field.name), default)
        return cls(**values)


def _coerce(raw, hint, default):
    """按声明的类型校验。`int | None` 这种可选类型要允许 None，但不接受字符串。"""
    if raw is None:
        return default
    candidates = [item for item in get_args(hint) if item is not type(None)]
    base = candidates[0] if candidates else hint

    if base is bool:
        return raw if isinstance(raw, bool) else default
    if base is int:
        return raw if isinstance(raw, int) and not isinstance(raw, bool) else default
    if base is float:
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return float(raw)
        return default
    if base is str:
        return raw if isinstance(raw, str) else default
    return default


def load(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AppConfig()
    if not isinstance(data, dict):
        return AppConfig()
    return AppConfig.from_dict(data)


def save(config: AppConfig, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target
