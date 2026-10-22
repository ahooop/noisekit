"""dB 时间序列曲线。

用固定量的环形数组，跑一整夜内存也不涨（设计文档 §11 的风险对策）。
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from apps.desktop.theme import ACCENT, GRID, PANEL, TEXT_DIM, WARN

FLOOR = -200.0


class TimeSeriesView(QWidget):
    def __init__(self, window_seconds: float = 300.0, parent=None) -> None:
        super().__init__(parent)
        self.window_seconds = float(window_seconds)
        self._points: deque[tuple[float, float]] = deque(maxlen=20000)
        self._lo = -90.0
        self._hi = 0.0
        self._threshold: float | None = None
        self._unit = "dB(A)"
        self.setMinimumHeight(150)

    # ------------------------------------------------------------------ 状态

    def set_range(self, lo: float, hi: float) -> None:
        self._lo, self._hi = float(lo), float(hi)
        self.update()

    def set_threshold(self, value: float | None) -> None:
        self._threshold = value
        self.update()

    def set_unit(self, unit: str) -> None:
        self._unit = unit
        self.update()

    def append(self, timestamp: float, value: float) -> None:
        if value <= FLOOR:
            return
        self._points.append((float(timestamp), float(value)))
        cutoff = timestamp - self.window_seconds * 1.2
        while self._points and self._points[0][0] < cutoff:
            self._points.popleft()
        self.update()

    def clear(self) -> None:
        self._points.clear()
        self.update()

    # ------------------------------------------------------------------ 绘制

    def _y(self, value: float, top: float, height: float) -> float:
        span = self._hi - self._lo
        frac = 0.0 if span <= 0 else min(max((value - self._lo) / span, 0.0), 1.0)
        return top + height * (1.0 - frac)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#12161c"))

        left, top = 44.0, 10.0
        right, bottom = 12.0, 22.0
        plot = QRectF(left, top, self.width() - left - right, self.height() - top - bottom)
        if plot.width() <= 1 or plot.height() <= 1:
            return

        painter.setPen(Qt.NoPen)
        painter.setBrush(PANEL)
        painter.drawRoundedRect(plot, 4, 4)

        # 横向网格与刻度
        painter.setFont(QFont("Segoe UI", 8))
        step = 10.0 if (self._hi - self._lo) >= 40 else 5.0
        value = self._lo
        while value <= self._hi + 1e-6:
            y = self._y(value, plot.top(), plot.height())
            painter.setPen(QPen(GRID, 1, Qt.DotLine))
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))
            painter.setPen(QPen(TEXT_DIM, 1))
            painter.drawText(QRectF(0, y - 7, left - 6, 14), Qt.AlignRight | Qt.AlignVCenter, f"{int(value)}")
            value += step

        # 阈值线
        if self._threshold is not None and self._lo <= self._threshold <= self._hi:
            y = self._y(self._threshold, plot.top(), plot.height())
            painter.setPen(QPen(WARN, 1, Qt.DashLine))
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))
            painter.setPen(QPen(WARN, 1))
            painter.drawText(
                QRectF(plot.right() - 90, y - 14, 86, 13),
                Qt.AlignRight | Qt.AlignVCenter,
                f"阈值 {self._threshold:.0f}",
            )

        # 折线
        points = list(self._points)
        if len(points) >= 2:
            now = points[-1][0]
            start = now - self.window_seconds
            visible = [p for p in points if p[0] >= start]
            if len(visible) >= 2:
                path = QPainterPath()
                for index, (ts, val) in enumerate(visible):
                    x = plot.left() + plot.width() * (1.0 - (now - ts) / self.window_seconds)
                    y = self._y(val, plot.top(), plot.height())
                    if index == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)
                painter.setPen(QPen(ACCENT, 1.6))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)

        # 单位与时间范围
        painter.setPen(QPen(TEXT_DIM, 1))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(plot.left(), plot.bottom() + 4, 200, 14), Qt.AlignLeft, self._unit)
        painter.drawText(
            QRectF(plot.right() - 200, plot.bottom() + 4, 200, 14),
            Qt.AlignRight,
            f"最近 {int(self.window_seconds)} 秒",
        )
