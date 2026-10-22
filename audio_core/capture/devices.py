"""输入设备枚举。

``sounddevice`` 是可选依赖：没装或不带 PortAudio 时，这里返回空列表而不是崩溃，
让 CLI 能给出一句人话的提示，而不是一段 traceback。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    channels: int
    default_samplerate: float
    is_default: bool = False

    def __str__(self) -> str:
        mark = " [默认]" if self.is_default else ""
        return f"{self.index}: {self.name} ({self.channels} 通道, {int(self.default_samplerate)} Hz){mark}"


def sounddevice_available() -> bool:
    try:
        import sounddevice  # noqa: F401
    except Exception:
        return False
    return True


def list_devices() -> list[DeviceInfo]:
    """返回所有具备输入通道的设备；后端不可用时返回空列表。"""
    try:
        import sounddevice as sd

        raw = sd.query_devices()
        default_in = sd.default.device[0]
    except Exception:
        return []

    devices: list[DeviceInfo] = []
    for idx, dev in enumerate(raw):
        channels = int(dev.get("max_input_channels", 0))
        if channels <= 0:
            continue
        devices.append(
            DeviceInfo(
                index=idx,
                name=str(dev.get("name", f"设备 {idx}")),
                channels=channels,
                default_samplerate=float(dev.get("default_samplerate", 0.0)),
                is_default=(idx == default_in),
            )
        )
    return devices


def find_device(selector: str | int) -> DeviceInfo | None:
    """按序号或名称子串查找设备，找不到返回 None。"""
    devices = list_devices()
    if isinstance(selector, int) or str(selector).isdigit():
        wanted = int(selector)
        for dev in devices:
            if dev.index == wanted:
                return dev
        return None
    needle = str(selector).lower()
    for dev in devices:
        if needle in dev.name.lower():
            return dev
    return None


def backend_info() -> dict[str, str]:
    """给 ``--doctor`` 用的后端诊断信息。"""
    info = {"backend": "unavailable"}
    try:
        import sounddevice as sd

        info["backend"] = str(sd.get_portaudio_version())
        info["hostapis"] = ", ".join(h["name"] for h in sd.query_hostapis())
        info["default_input"] = str(sd.default.device[0])
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info
