"""主窗口：设备选择、实时显示、状态栏。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from apps.desktop.theme import TEXT_DIM, WARN
from apps.desktop.widgets import LevelMeter, SpectrumView, TimeSeriesView
from apps.desktop.worker import AnalysisWorker
from audio_core import __version__
from audio_core.capture.devices import list_devices

SYNTHETIC_LABEL = "模拟：1 kHz 正弦（无需麦克风）"

DISCLAIMER = (
    "本软件使用消费级麦克风配合软件计算声级，不是计量认证仪器，"
    "结果仅供参考与趋势对比，不得用于执法取证、工程验收或法定检测。"
)


class MainWindow(QMainWindow):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"NoiseKit {__version__} — 环境噪声监测")
        self.resize(980, 720)

        self._worker: AnalysisWorker | None = None
        self._elapsed = 0.0
        self._fps = 0
        self._fps_frames = 0
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(1000)
        self._fps_timer.timeout.connect(self._tick_fps)

        self._build_ui()
        self._reload_devices()

    # ------------------------------------------------------------------ 构建

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(10)

        # 顶部控制条
        controls = QHBoxLayout()
        controls.setSpacing(8)

        controls.addWidget(QLabel("输入设备"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(320)
        controls.addWidget(self.device_combo, 1)

        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self._reload_devices)
        controls.addWidget(self.refresh_button)

        controls.addWidget(QLabel("校准偏移"))
        self.calibration_spin = QDoubleSpinBox()
        self.calibration_spin.setRange(-200.0, 200.0)
        self.calibration_spin.setDecimals(1)
        self.calibration_spin.setSingleStep(0.5)
        self.calibration_spin.setValue(0.0)
        self.calibration_spin.setToolTip(
            "dB SPL = dBFS + 偏移。留 0 并在下方取消「已校准」，读数将标注为相对值。"
        )
        controls.addWidget(self.calibration_spin)

        self.calibrated_combo = QComboBox()
        self.calibrated_combo.addItems(["未校准（相对值）", "已校准（dB SPL）"])
        controls.addWidget(self.calibrated_combo)

        self.start_button = QPushButton("开始")
        self.start_button.clicked.connect(self.start)
        controls.addWidget(self.start_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.stop_button)

        root.addLayout(controls)

        # 电平表
        self.level_meter = LevelMeter()
        root.addWidget(self.level_meter)

        # 指标块
        metrics_box = QGroupBox("指标")
        grid = QGridLayout(metrics_box)
        grid.setHorizontalSpacing(18)
        self._metric_labels: dict[str, QLabel] = {}
        entries = [
            ("leq_1s", "Leq(1s)"),
            ("leq_10s", "Leq(10s)"),
            ("leq_session", "Leq(会话)"),
            ("lafmax", "LAFmax"),
            ("lcpeak", "LCpeak"),
        ]
        for column, (key, title) in enumerate(entries):
            caption = QLabel(title)
            caption.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 11px;")
            value = QLabel("--.-")
            value.setFont(QFont("Segoe UI", 15, QFont.Bold))
            value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            grid.addWidget(caption, 0, column)
            grid.addWidget(value, 1, column)
            self._metric_labels[key] = value
        root.addWidget(metrics_box)

        # 曲线
        self.time_series = TimeSeriesView(window_seconds=300)
        series_box = QGroupBox("声级曲线")
        series_layout = QVBoxLayout(series_box)
        series_layout.setContentsMargins(6, 6, 6, 6)
        series_layout.addWidget(self.time_series)
        root.addWidget(series_box, 3)

        # 频谱
        self.spectrum = SpectrumView()
        spectrum_box = QGroupBox("实时频谱")
        spectrum_layout = QVBoxLayout(spectrum_box)
        spectrum_layout.setContentsMargins(6, 6, 6, 6)
        spectrum_layout.addWidget(self.spectrum)
        root.addWidget(spectrum_box, 2)

        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet(f"color: {WARN.name()}; font-size: 11px;")
        root.addWidget(disclaimer)

        self.setCentralWidget(central)
        self.statusBar().showMessage("就绪")

    # ------------------------------------------------------------------ 设备

    def _reload_devices(self) -> None:
        self.device_combo.clear()
        devices = list_devices()
        for dev in devices:
            self.device_combo.addItem(str(dev), userData=dev.index)
        self.device_combo.addItem(SYNTHETIC_LABEL, userData="synthetic")
        if not devices:
            self.statusBar().showMessage("未检测到输入设备，可先用「模拟信号」查看界面")

    # ------------------------------------------------------------------ 采集

    def _create_source(self):
        data = self.device_combo.currentData()
        if data == "synthetic":
            from audio_core.capture.synthetic import SyntheticSource

            return SyntheticSource(
                sample_rate=48000, freq=1000.0, amplitude=0.5, realtime=True
            )
        from audio_core.capture.stream import SoundDeviceSource

        return SoundDeviceSource(device=data)

    def start(self) -> None:
        if self._worker is not None:
            return
        try:
            source = self._create_source()
        except Exception as exc:
            QMessageBox.critical(self, "无法打开设备", f"{type(exc).__name__}: {exc}")
            return

        calibrated = self.calibrated_combo.currentIndex() == 1
        offset = self.calibration_spin.value() if calibrated else None
        lo, hi = (30.0, 120.0) if calibrated else (-90.0, 0.0)
        unit = "dB(A) SPL" if calibrated else "dB(A) 相对"
        self.level_meter.set_range(lo, hi)
        self.level_meter.set_unit(unit)
        self.level_meter.set_caption(f"{source.sample_rate} Hz · {source.block_frames} 帧/块")
        self.time_series.set_range(lo, hi)
        self.time_series.set_unit(unit)
        self.time_series.set_threshold(65.0 if calibrated else -30.0)
        self.time_series.clear()
        self.spectrum.clear()
        self.level_meter.reset()
        for label in self._metric_labels.values():
            label.setText("--.-")

        self._elapsed = 0.0
        self._fps_frames = 0
        self._fps = 0
        self._fps_timer.start()

        worker = AnalysisWorker(source, calibration_offset=offset)
        worker.frame_ready.connect(self._on_frame)
        worker.spectrum_ready.connect(self._on_spectrum)
        worker.failed.connect(self._on_failed)
        worker.stopped.connect(self._on_stopped)
        self._worker = worker
        worker.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.device_combo.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.statusBar().showMessage("采集中…")

    def stop(self) -> None:
        if self._worker is None:
            return
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("正在停止…")
        self._worker.stop()

    # ------------------------------------------------------------------ 回调

    def _on_frame(self, frame) -> None:
        self._fps_frames += 1
        level = frame.display_level()
        self.level_meter.set_level(level, peak=max(frame.lafmax, level))
        self.time_series.append(frame.ts, level)
        self._elapsed = frame.ts

        values = {
            "leq_1s": frame.leq_1s,
            "leq_10s": frame.leq_10s,
            "leq_session": frame.leq_session,
            "lafmax": frame.lafmax,
            "lcpeak": frame.lcpeak,
        }
        for key, label in self._metric_labels.items():
            label.setText(f"{values[key]:.1f}")

        overflows = getattr(self._worker.source, "_ring", None)
        dropped = overflows.overflows if overflows is not None else 0
        self.statusBar().showMessage(
            f"采集中 · 已分析 {self._elapsed:.0f} 秒 · {self._fps} fps · 掉帧事件 {dropped}"
        )

    def _on_spectrum(self, freqs, db) -> None:
        self.spectrum.set_spectrum(freqs, db)

    def _on_failed(self, message: str) -> None:
        self.statusBar().showMessage(f"采集出错：{message}")
        QMessageBox.warning(self, "采集出错", message)

    def _on_stopped(self, analyzed_seconds: float) -> None:
        self._fps_timer.stop()
        if self._worker is not None:
            self._worker.wait(2000)
            self._worker = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.device_combo.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.statusBar().showMessage(f"已停止，本次分析 {analyzed_seconds:.0f} 秒音频")

    def _tick_fps(self) -> None:
        self._fps = self._fps_frames
        self._fps_frames = 0

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(2000)
            self._worker = None
        super().closeEvent(event)
