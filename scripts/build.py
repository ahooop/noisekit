"""把桌面端打包成可双击运行的程序。

    python scripts/build.py

产物在 ``dist/NoiseKit/``。注意两件事：

* **必须显式带上 PortAudio 动态库**。``sounddevice`` 通过 ``_sounddevice_data``
  在运行时加载 DLL，PyInstaller 的静态分析看不到这一步；漏了的表现是
  「程序能启动，但一个设备都找不到」。
* 用 ``--windowed``：用户不应该看到黑色控制台窗口。代价是拿不到 stdout，
  所以冒烟测试只看退出码（``--selftest`` 返回 0/1）。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
NAME = "NoiseKit"

EXCLUDES = (
    # 开发用的
    "tkinter",
    "pytest",
    "IPython",
    "notebook",
    "jupyter",
    # 其他 Qt 绑定，我们只用 PySide6
    "PyQt5",
    "PyQt6",
    # 这台机器上装了但本项目一行都不用的重型依赖：不排掉会多打 800 MB。
    # 不装这些库的机器上这些参数是无害的空操作。
    "torch",
    "torchvision",
    "cv2",
    "transformers",
    "onnxruntime",
    "duckdb",
    "openvino",
    "pandas",
    "babel",
    "matplotlib",
    "numba",
    "llvmlite",
    "sympy",
    "sklearn",
    "tensorflow",
    "jax",
    "h5py",
    "tables",
    "numexpr",
)


def portaudio_data_dir() -> Path:
    import _sounddevice_data

    return Path(_sounddevice_data.__file__).parent


def main() -> int:
    data_dir = portaudio_data_dir()
    if not data_dir.exists():
        print(f"找不到 PortAudio 目录：{data_dir}", file=sys.stderr)
        return 1

    sep = ";" if sys.platform == "win32" else ":"
    for stale in (DIST / NAME, BUILD / NAME):
        if stale.exists():
            shutil.rmtree(stale, ignore_errors=True)

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        NAME,
        "--windowed",
        "--paths",
        str(ROOT),
        "--add-data",
        f"{data_dir}{sep}_sounddevice_data",
        "--hidden-import",
        "_sounddevice_data",
        "--hidden-import",
        "sounddevice",
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        str(ROOT / "apps" / "desktop" / "main.py"),
    ]
    for module in EXCLUDES:
        args.extend(["--exclude-module", module])

    print("执行：", " ".join(args))
    result = subprocess.run(args, cwd=ROOT, check=False)
    if result.returncode != 0:
        print("打包失败", file=sys.stderr)
        return result.returncode

    target = DIST / NAME
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) / 1024 / 1024
    print(f"打包完成：{target}（{size:.0f} MB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
