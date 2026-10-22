"""media-core 的公共数据类型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class FrameSample:
    """一帧画面。timestamp 为源视频中的秒数。"""

    timestamp: float
    path: Path

    def to_dict(self) -> dict:
        return {"timestamp": round(self.timestamp, 3), "path": self.path.name}
