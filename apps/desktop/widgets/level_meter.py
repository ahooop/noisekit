"""电平表：大字号读数 + 带刻度的色条。"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from apps.desktop.theme import GRID, LEVEL_HIGH, LEVEL_LOW, LEVEL_MID, PANEL, TEXT, TEXT_DIM

FLOOR = -200.0


class LevelMeter(QWidget):
    """横向电平条。颜色按当前数值在量程中的位置渐变。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._level = FLOOR
        self._peak = FLOOR
        self._lo = -90.0
        self._hi = 0.0
        self._unit = "dB(A)"
        self._caption = "未开始"
        self.setMinimumHeight(120)

    # ------------------------------------------------------------------ 状态

    def set_range(self, lo: float, hi: float) -> None:
        self._lo, self._hi = float(lo), float(hi)
        self.update()

    def set_unit(self, unit: str) -> None:
        self._unit = unit
        self.update()

    def set_caption(self, caption: str) -> None:
        self._caption = caption
        self.update()

    def set_level(self, level: float, peak: float | None = None) -> None:
        self._level = float(level)
        if peak is not None:
            self._peak = float(peak)
        self.update()

    def reset(self) -> None:
        self._level = FLOOR
        self._peak = FLOOR
        self.update()

    # ------------------------------------------------------------------ 绘制

    def _fraction(self, value: float) -> float:
        span = self._hi - self._lo
        if span <= 0:
            return 0.0
        return min(max((value - self._lo) / span, 0.0), 1.0)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 接口
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#12161c"))

        width = self.width()
        height = self.height()
        bar_height = 18.0
        bar_top = height - 46.0
        bar_rect = QRectF(16.0, bar_top, width - 32.0, bar_height)

        # 底部轨道
        painter.setPen(Qt.NoPen)
        painter.setBrush(PANEL)
        painter.drawRoundedRect(bar_rect, 4, 4)

        fraction = self._fraction(self._level) if self._level > FLOOR else 0.0
        if fraction > 0:
            filled = QRectF(bar_rect.left(), bar_rect.top(), bar_rect.width() * fraction, bar_height)
            gradient = QLinearGradient(bar_rect.left(), 0, bar_rect.right(), 0)
            gradient.setColorAt(0.0, LEVEL_LOW)
            gradient.setColorAt(0.65, LEVEL_MID)
            gradient.setColorAt(1.0, LEVEL_HIGH)
            painter.setBrush(gradient)
            painter.drawRoundedRect(filled, 4, 4)

        # 峰值标记
        if self._peak > FLOOR:
            x = bar_rect.left() + bar_rect.width() * self._fraction(self._peak)
            painter.setPen(QPen(TEXT, 2))
            painter.drawLine(int(x), int(bar_top - 3), int(x), int(bar_top + bar_height + 3))

        # 刻度
        painter.setPen(QPen(GRID, 1))
        painter.setFont(QFont("Segoe UI", 8))
        step = 10.0 if (self._hi - self._lo) >= 40 else 5.0
        value = self._lo
        while value <= self._hi + 1e-6:
            x = bar_rect.left() + bar_rect.width() * self._fraction(value)
            painter.setPen(QPen(GRID, 1))
            painter.drawLine(int(x), int(bar_top + bar_height), int(x), int(bar_top + bar_height + 4))
            painter.setPen(QPen(TEXT_DIM, 1))
            painter.drawText(
                QRectF(x - 16, bar_top + bar_height + 5, 32, 14),
                Qt.AlignHCenter | Qt.AlignTop,
                f"{int(value)}",
            )
            value += step

        # 主读数
        text = f"{self._level:.1f}" if self._level > FLOOR else "--.-"
        painter.setPen(QPen(TEXT, 1))
        painter.setFont(QFont("Segoe UI", 34, QFont.Bold))
        painter.drawText(
            QRectF(16, 2, width - 120, 56), Qt.AlignLeft | Qt.AlignVCenter, text
        )
        painter.setFont(QFont("Segoe UI", 12))
        painter.setPen(QPen(TEXT_DIM, 1))
        painter.drawText(
            QRectF(width - 110, 2, 94, 56), Qt.AlignRight | Qt.AlignVCenter, self._unit
        )
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRectF(16, bar_top - 26, width - 32, 18), Qt.AlignLeft, self._caption)
