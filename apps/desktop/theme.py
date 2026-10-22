"""界面主题：深色、低对比干扰，看曲线时眼睛不累。"""

from __future__ import annotations

from PySide6.QtGui import QColor

BG = QColor("#12161c")
PANEL = QColor("#1a2029")
GRID = QColor("#2a3341")
TEXT = QColor("#c9d4e3")
TEXT_DIM = QColor("#7d8b9e")
ACCENT = QColor("#4fc3f7")
ACCENT_DIM = QColor("#24708f")
WARN = QColor("#ff7043")
OK = QColor("#66bb6a")
LEVEL_LOW = QColor("#66bb6a")
LEVEL_MID = QColor("#ffca28")
LEVEL_HIGH = QColor("#ef5350")

STYLE_SHEET = """
QMainWindow, QWidget { background-color: #12161c; color: #c9d4e3; }
QGroupBox {
    border: 1px solid #2a3341; border-radius: 6px; margin-top: 10px; padding-top: 6px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #7d8b9e; }
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {
    background-color: #1a2029; border: 1px solid #2a3341; border-radius: 4px;
    padding: 3px 6px; color: #c9d4e3;
}
QComboBox::drop-down { border: none; }
QPushButton {
    background-color: #24708f; border: none; border-radius: 4px;
    padding: 6px 16px; color: #eaf6ff; font-weight: 600;
}
QPushButton:hover { background-color: #2e86ab; }
QPushButton:disabled { background-color: #2a3341; color: #5c6775; }
QPushButton#stopButton { background-color: #a33b2a; }
QPushButton#stopButton:hover { background-color: #c04a36; }
QStatusBar { color: #7d8b9e; }
"""
