"""实时频谱：对数频率轴，20 Hz – 20 kHz。"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from apps.desktop.theme import ACCENT, GRID, PANEL, TEXT_DIM

F_MIN = 20.0
F_MAX = 20000.0
DB_MIN = -100.0
DB_MAX = 0.0


class SpectrumView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._freqs: np.ndarray | None = None
        self._db: np.ndarray | None = None
        self.setMinimumHeight(180)

    def set_spectrum(self, freqs: np.ndarray, db: np.ndarray) -> None:
        self._freqs = np.asarray(freqs, dtype=float)
        self._db = np.asarray(db, dtype=float)
        self.update()

    def clear(self) -> None:
        self._freqs = None
        self._db = None
        self.update()

    def _x(self, freq: float, plot: QRectF) -> float:
        freq = max(freq, F_MIN)
        ratio = np.log10(freq / F_MIN) / np.log10(F_MAX / F_MIN)
        return plot.left() + plot.width() * min(max(ratio, 0.0), 1.0)

    def _y(self, db: float, plot: QRectF) -> float:
        frac = (min(max(db, DB_MIN), DB_MAX) - DB_MIN) / (DB_MAX - DB_MIN)
        return plot.top() + plot.height() * (1.0 - frac)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#12161c"))

        left, top = 44.0, 10.0
        right, bottom = 12.0, 34.0
        plot = QRectF(left, top, self.width() - left - right, self.height() - top - bottom)
        if plot.width() <= 1 or plot.height() <= 1:
            return

        painter.setPen(Qt.NoPen)
        painter.setBrush(PANEL)
        painter.drawRoundedRect(plot, 4, 4)

        painter.setFont(QFont("Segoe UI", 8))
        # 纵向网格（频率）与横向网格（dB）
        for freq in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
            x = self._x(freq, plot)
            painter.setPen(QPen(GRID, 1, Qt.DotLine))
            painter.drawLine(int(x), int(plot.top()), int(x), int(plot.bottom()))
            label = f"{freq // 1000}k" if freq >= 1000 else str(freq)
            painter.setPen(QPen(TEXT_DIM, 1))
            painter.drawText(QRectF(x - 18, plot.bottom() + 2, 36, 13), Qt.AlignHCenter, label)

        for db in range(-100, 1, 20):
            y = self._y(db, plot)
            painter.setPen(QPen(GRID, 1, Qt.DotLine))
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))
            painter.setPen(QPen(TEXT_DIM, 1))
            painter.drawText(QRectF(0, y - 7, left - 6, 14), Qt.AlignRight | Qt.AlignVCenter, f"{db}")

        if self._freqs is not None and self._db is not None:
            mask = self._freqs >= F_MIN
            freqs = self._freqs[mask]
            db = self._db[mask]
            if freqs.size >= 2:
                path = QPainterPath()
                path.moveTo(self._x(freqs[0], plot), plot.bottom())
                for freq, value in zip(freqs, db, strict=False):
                    path.lineTo(self._x(freq, plot), self._y(value, plot))
                path.lineTo(self._x(freqs[-1], plot), plot.bottom())
                path.closeSubpath()

                gradient = QLinearGradient(0, plot.top(), 0, plot.bottom())
                fill_top = QColor(ACCENT)
                fill_top.setAlpha(110)
                fill_bottom = QColor(ACCENT)
                fill_bottom.setAlpha(10)
                gradient.setColorAt(0.0, fill_top)
                gradient.setColorAt(1.0, fill_bottom)
                painter.setPen(Qt.NoPen)
                painter.setBrush(gradient)
                painter.drawPath(path)

                line = QPainterPath()
                for index, (freq, value) in enumerate(zip(freqs, db, strict=False)):
                    x, y = self._x(freq, plot), self._y(value, plot)
                    if index == 0:
                        line.moveTo(x, y)
                    else:
                        line.lineTo(x, y)
                painter.setPen(QPen(ACCENT, 1.2))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(line)

        painter.setPen(QPen(TEXT_DIM, 1))
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 16, 300, 14), Qt.AlignLeft, "频率 Hz（对数刻度）"
        )
        painter.drawText(
            QRectF(plot.right() - 300, plot.bottom() + 16, 300, 14),
            Qt.AlignRight,
            "峰值幅度 dBFS",
        )
