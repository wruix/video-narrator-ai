"""media-core：与厂商无关的视频处理内核。

包含 FFmpeg 封装、镜头切分、关键帧抽取、字幕生成与成片合成。
API 服务与 Worker 都只依赖这个包，不直接调用 FFmpeg。
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["compose", "config", "frames", "media", "subtitle"]
