"""主窗口：设备选择、实时显示、状态栏。"""

from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
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
        self._session = None
        self._report_path: Path | None = None
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
        self.calibrated_combo.currentIndexChanged.connect(self._on_calibration_mode_changed)
        controls.addWidget(self.calibrated_combo)

        controls.addWidget(QLabel("阈值"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(-120.0, 200.0)
        self.threshold_spin.setDecimals(0)
        self.threshold_spin.setValue(-30.0)
        self.threshold_spin.setToolTip("超过该值并持续 3 秒即留证；未校准时为相对 dB")
        controls.addWidget(self.threshold_spin)

        self.start_button = QPushButton("开始")
        self.start_button.clicked.connect(self.start)
        controls.addWidget(self.start_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.stop_button)

        self.record_check = QCheckBox("留证记录")
        self.record_check.setChecked(True)
        self.record_check.setToolTip("把指标写入 SQLite，超标时保存前置缓冲 + 事件录音，停止后生成报告")
        controls.addWidget(self.record_check)

        self.report_button = QPushButton("打开报告")
        self.report_button.setEnabled(False)
        self.report_button.clicked.connect(self._open_report)
        controls.addWidget(self.report_button)

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

        # 事件留证
        self.event_list = QListWidget()
        self.event_list.setMaximumHeight(90)
        self.event_list.addItem("暂无超标事件")
        events_box = QGroupBox("超标事件（自动留证）")
        events_box.setMaximumHeight(132)
        events_layout = QVBoxLayout(events_box)
        events_layout.setContentsMargins(6, 4, 6, 6)
        events_layout.addWidget(self.event_list)
        root.addWidget(events_box)

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
        self.time_series.set_threshold(self.threshold_spin.value())
        self.time_series.clear()
        self.spectrum.clear()
        self.level_meter.reset()
        for label in self._metric_labels.values():
            label.setText("--.-")

        self._elapsed = 0.0
        self._fps_frames = 0
        self._fps = 0
        self._fps_timer.start()

        self._session = self._open_session(source, offset)

        worker = AnalysisWorker(source, calibration_offset=offset, session=self._session)
        worker.frame_ready.connect(self._on_frame)
        worker.spectrum_ready.connect(self._on_spectrum)
        worker.event_ready.connect(self._on_event)
        worker.failed.connect(self._on_failed)
        worker.stopped.connect(self._on_stopped)
        self._worker = worker
        worker.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.device_combo.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.record_check.setEnabled(False)
        self.statusBar().showMessage("采集中…")

    def _open_session(self, source, offset: float | None):
        if not self.record_check.isChecked():
            return None
        from audio_core.session import RecordingSession

        root = Path.cwd() / "sessions" / datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            session = RecordingSession(
                root=root,
                device_name=self.device_combo.currentText(),
                sample_rate=source.sample_rate,
                calibration_offset=offset,
                threshold=self.threshold_spin.value(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "无法建立会话", f"{type(exc).__name__}: {exc}")
            return None
        self.event_list.clear()
        return session

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

    def _on_event(self, kind: str, event) -> None:
        if kind == "start":
            self.event_list.addItem(
                f"[开始] {event.started_at:7.1f}s 超标（阈值 {event.threshold:.0f}）"
            )
        else:
            name = Path(event.audio_path).name if event.audio_path else "未录音"
            self.event_list.addItem(
                f"[结束] {event.started_at:7.1f}s · 持续 {event.duration:.1f}s · "
                f"峰值 {event.peak:.1f} · {name}"
            )
        self.event_list.scrollToBottom()

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
        self.record_check.setEnabled(True)

        message = f"已停止，本次分析 {analyzed_seconds:.0f} 秒音频"
        if self._session is not None:
            session, self._session = self._session, None
            try:
                summary = session.close()
                report = session.export_report()
                self._report_path = report
                self.report_button.setEnabled(True)
                events = len(summary.events) if summary else 0
                message = f"已停止 · 会话 #{summary.id if summary else '?'} 已保存 · 报告：{report}"
                self.event_list.addItem(f"报告已生成：{report}")
                del events
            except Exception as exc:
                message = f"已停止，但保存失败：{type(exc).__name__}: {exc}"
        self.statusBar().showMessage(message)

    def _open_report(self) -> None:
        if self._report_path and self._report_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._report_path)))

    def _on_calibration_mode_changed(self, index: int) -> None:
        self.threshold_spin.setValue(65.0 if index == 1 else -30.0)

    def _tick_fps(self) -> None:
        self._fps = self._fps_frames
        self._fps_frames = 0

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(2000)
            self._worker = None
        if self._session is not None:
            with contextlib.suppress(Exception):
                self._session.close()
            self._session = None
        super().closeEvent(event)
