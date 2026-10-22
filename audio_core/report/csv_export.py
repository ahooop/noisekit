"""指标表导出。"""

from __future__ import annotations

import csv
from pathlib import Path

from ..metrics.meter import FrameMetrics

COLUMNS = (
    "ts",
    "dbfs",
    "db_a",
    "db_c",
    "spl",
    "spl_a",
    "spl_c",
    "leq_1s",
    "leq_10s",
    "lafmax",
    "lcpeak",
)


def write_csv(path: str | Path, frames: list[FrameMetrics]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for frame in frames:
            writer.writerow([getattr(frame, column) for column in COLUMNS])
    return target
