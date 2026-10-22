"""插件注册表与架构约束的测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from audio_core import analyzers


def test_only_noise_is_implemented() -> None:
    assert analyzers.available() == ["noise"]


def test_planned_analyzers_are_visible_but_disabled() -> None:
    planned = analyzers.available(include_unimplemented=True)
    assert set(planned) == {"noise", "music", "voice", "device"}
    for name in ("music", "voice", "device"):
        with pytest.raises(NotImplementedError):
            analyzers.create(name)


def test_unknown_analyzer_raises() -> None:
    with pytest.raises(KeyError):
        analyzers.create("theremin")


def test_noise_analyzer_emits_expected_fields() -> None:
    analyzer = analyzers.create("noise", sample_rate=48000)
    block = __import__("numpy").zeros(480, dtype="float32")
    payload = analyzer.process(block, 0.0)
    expected = {
        "ts",
        "dbfs",
        "db_a",
        "db_c",
        "laf",
        "las",
        "leq_1s",
        "leq_10s",
        "leq_session",
        "lafmax",
        "lcpeak",
        "spl",
        "spl_a",
        "spl_c",
    }
    assert expected.issubset(payload.keys())


def test_core_has_no_gui_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "audio_core"
    banned = ("PySide6", "PyQt5", "PyQt6", "tkinter")
    offenders = []
    for path in root.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and any(b in stripped for b in banned):
                offenders.append(f"{path.name}:{lineno}")
    assert not offenders, f"audio_core 不得依赖 GUI：{offenders}"
