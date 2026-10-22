"""校准向导。

声级计必须校准才有绝对值。这里支持两条路：

1. **声级校准器**：套在麦克风上，通常是 94 dB @ 1 kHz，直接把 94 填进去；
2. **参考声级计**：手边有可信仪器时，让它和 NoiseKit 同时测同一段声音，
   把仪器读数填进去。

原理一样：``偏移 = 参考声压级 − 当前读数``。
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from audio_core.dsp.framing import mean_square
from audio_core.dsp.level import calibration_offset, mean_square_to_db

MEASURE_SECONDS = 2.0


class CalibrationDialog(QDialog):
    def __init__(self, device, sample_rate: int, parent=None) -> None:
        super().__init__(parent)
        self.device = device
        self.sample_rate = sample_rate
        self._offset: float | None = None
        self._measured_dbfs: float | None = None

        self.setWindowTitle("校准向导")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "把参考声压级填进下面，然后点「测量 2 秒」。\n\n"
            "· 有声级校准器：套在麦克风上，通常标称 94 dB\n"
            "· 没有校准器：用可信的声级计与 NoiseKit 同时测同一段声音，填它的读数\n\n"
            "测量期间请保持环境声音稳定，不要说话。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.ref_spin = QDoubleSpinBox()
        self.ref_spin.setRange(30.0, 140.0)
        self.ref_spin.setDecimals(1)
        self.ref_spin.setValue(94.0)
        self.ref_spin.setSuffix(" dB SPL")
        form.addRow("参考声压级", self.ref_spin)
        layout.addLayout(form)

        self.measure_button = QPushButton("测量 2 秒")
        self.measure_button.clicked.connect(self._measure)
        layout.addWidget(self.measure_button)

        self.result_label = QLabel("尚未测量")
        self.result_label.setWordWrap(True)
        self.result_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(self.result_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    # ------------------------------------------------------------------ 测量

    @property
    def offset(self) -> float | None:
        return self._offset

    def _measure(self) -> None:
        from audio_core.capture.source import SourceError
        from audio_core.capture.stream import SoundDeviceSource

        self.measure_button.setEnabled(False)
        self.result_label.setText("正在采集…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        chunks: list[np.ndarray] = []
        received = 0
        try:
            source = SoundDeviceSource(device=self.device, ring_seconds=3.0, idle_timeout=3.0)
            needed = int(MEASURE_SECONDS * source.sample_rate)
            try:
                for block in source.blocks():
                    chunks.append(block)
                    received += block.size
                    self.result_label.setText(
                        f"正在采集… {min(received / source.sample_rate, MEASURE_SECONDS):.1f} / "
                        f"{MEASURE_SECONDS:.0f} 秒"
                    )
                    QApplication.processEvents()
                    if received >= needed:
                        break
            finally:
                source.close()
        except SourceError as exc:
            QApplication.restoreOverrideCursor()
            self.measure_button.setEnabled(True)
            self.result_label.setText("测量失败")
            QMessageBox.warning(self, "无法采集", str(exc))
            return
        except Exception as exc:  # 设备层什么都可能抛
            QApplication.restoreOverrideCursor()
            self.measure_button.setEnabled(True)
            self.result_label.setText("测量失败")
            QMessageBox.warning(self, "校准失败", f"{type(exc).__name__}: {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        if not chunks:
            self.measure_button.setEnabled(True)
            self.result_label.setText("没有收到任何音频")
            return

        samples = np.concatenate(chunks)
        measured = mean_square_to_db(mean_square(samples))
        if measured <= -199.0:
            self.measure_button.setEnabled(True)
            self.result_label.setText("麦克风没有信号，请检查是否静音")
            return

        self._measured_dbfs = measured
        self._offset = calibration_offset(self.ref_spin.value(), measured)
        self.result_label.setText(
            f"实测 {measured:.1f} dBFS\n"
            f"校准偏移 {self._offset:+.1f} dB\n"
            f"之后读数 = dBFS {self._offset:+.1f}"
        )
        self.measure_button.setEnabled(True)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)
