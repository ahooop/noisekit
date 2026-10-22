"""配置读写测试：坏配置不能让程序起不来。"""

from __future__ import annotations

import json

from audio_core import config


def test_missing_file_returns_defaults(tmp_path) -> None:
    cfg = config.load(tmp_path / "nope.json")
    assert isinstance(cfg, config.AppConfig)
    assert cfg.calibrated is False
    assert cfg.threshold == -30.0


def test_roundtrip(tmp_path) -> None:
    path = tmp_path / "config.json"
    original = config.AppConfig(
        device_index=6,
        calibrated=True,
        calibration_offset=124.5,
        threshold=65.0,
        output_dir="D:/noise",
    )
    config.save(original, path)
    loaded = config.load(path)
    assert loaded == original


def test_saved_file_is_human_readable(tmp_path) -> None:
    path = config.save(config.AppConfig(device_index=3), tmp_path / "c.json")
    text = path.read_text(encoding="utf-8")
    assert "device_index" in text
    assert "\n" in text  # 缩进过，方便用户手改


def test_corrupt_json_falls_back(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{ 这不是 json", encoding="utf-8")
    assert config.load(path) == config.AppConfig()


def test_wrong_types_are_ignored(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"device_index": "六", "calibrated": "yes", "threshold": None}),
        encoding="utf-8",
    )
    cfg = config.load(path)
    assert cfg.device_index is None
    assert cfg.calibrated is False
    assert cfg.threshold == -30.0


def test_unknown_keys_are_dropped(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"threshold": 70.0, "未来的字段": 1}), encoding="utf-8")
    cfg = config.load(path)
    assert cfg.threshold == 70.0
    assert not hasattr(cfg, "未来的字段")


def test_non_dict_json_falls_back(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert config.load(path) == config.AppConfig()


def test_config_path_is_under_user_dir() -> None:
    path = config.config_path()
    assert path.name == "config.json"
    assert "NoiseKit" in str(path)
