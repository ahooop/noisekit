"""界面冒烟测试：能构造、能画、不抛异常。

没有装 PySide6 的机器上自动跳过，所以 CI 的三平台矩阵不会被 GUI 拖住。
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from apps.desktop.widgets import LevelMeter, SpectrumView, TimeSeriesView  # noqa: E402
from apps.desktop.windows import MainWindow  # noqa: E402
from audio_core.dsp.spectrum import spectrum_db  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_builds(qapp) -> None:
    window = MainWindow()
    assert window.device_combo.count() >= 1  # 至少要有「模拟信号」这一项
    assert window.start_button.isEnabled()
    assert not window.stop_button.isEnabled()
    window.close()


def test_level_meter_paints(qapp) -> None:
    meter = LevelMeter()
    meter.set_range(-90, 0)
    meter.set_level(-12.5, peak=-9.0)
    pixmap = meter.grab()
    assert not pixmap.isNull()
    assert pixmap.width() > 0


def test_time_series_paints(qapp) -> None:
    view = TimeSeriesView(window_seconds=60)
    view.set_range(-90, 0)
    view.set_threshold(-30)
    for i in range(120):
        view.append(i * 0.5, -40 + 5 * np.sin(i / 8))
    assert not view.grab().isNull()


def test_spectrum_paints(qapp) -> None:
    view = SpectrumView()
    freqs, db = spectrum_db(np.random.default_rng(0).standard_normal(2048) * 0.1, 48000)
    view.set_spectrum(freqs, db)
    assert not view.grab().isNull()


def test_synthetic_source_drives_window(qapp) -> None:
    """点「开始」后应能收到真实的分析结果，而不是只有空界面。"""
    from PySide6.QtCore import QTimer

    window = MainWindow()
    window.show()
    index = window.device_combo.findData("synthetic")
    window.device_combo.setCurrentIndex(index)
    window.start()

    received: list[object] = []
    window._worker.frame_ready.connect(received.append)

    # 用 quit() 退出事件循环，而不是 close()：
    # 未显示的窗口调用 close() 不会派发 closeEvent，事件循环会一直转下去
    QTimer.singleShot(1500, qapp.quit)
    qapp.exec()

    window.stop()
    if window._worker is not None:
        window._worker.wait(2000)
    window.close()

    assert received, "没有收到任何帧"
    assert received[-1].dbfs < 0
