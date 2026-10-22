"""media-core 的运行配置。

这些参数只跟「本机媒体处理」有关，因此放在可复用包里，
API 服务与 Worker 都会引用同一份定义。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Binaries:
    """FFmpeg / FFprobe 可执行文件定位。"""

    ffmpeg: str = field(default_factory=lambda: os.getenv("VC_FFMPEG", "ffmpeg"))
    ffprobe: str = field(default_factory=lambda: os.getenv("VC_FFPROBE", "ffprobe"))

    def resolve(self, which: str) -> str | None:
        candidate = getattr(self, which)
        if os.path.isabs(candidate) and Path(candidate).exists():
            return candidate
        return shutil.which(candidate)


BIN = Binaries()


def ffmpeg_bin() -> str:
    exe = BIN.resolve("ffmpeg")
    if not exe:
        raise RuntimeError(
            "未找到 ffmpeg。请安装 FFmpeg 并加入 PATH，或设置环境变量 VC_FFMPEG 指向可执行文件。"
        )
    return exe


def ffprobe_bin() -> str:
    exe = BIN.resolve("ffprobe")
    if not exe:
        raise RuntimeError(
            "未找到 ffprobe。请安装 FFmpeg 并加入 PATH，或设置环境变量 VC_FFPROBE 指向可执行文件。"
        )
    return exe


# ---------------------------------------------------------------- 抽帧与切分

# 兜底抽帧间隔（秒）
DEFAULT_FRAME_INTERVAL = float(os.getenv("VC_FRAME_INTERVAL", "2.0"))
MIN_FRAMES_PER_SHOT = 1
MAX_FRAMES_PER_SHOT = int(os.getenv("VC_MAX_FRAMES_PER_SHOT", "8"))
MAX_FRAMES_TOTAL = int(os.getenv("VC_MAX_FRAMES_TOTAL", "160"))
# 场景切换阈值（0-1，越小切分越细）
SCENE_THRESHOLD = float(os.getenv("VC_SCENE_THRESHOLD", "0.28"))
# 帧间差异超过该值判定为「快速运动」，触发补帧
MOTION_THRESHOLD = float(os.getenv("VC_MOTION_THRESHOLD", "18.0"))

# ---------------------------------------------------------------- 字幕

# Windows 用微软雅黑，Linux 通常用 Noto Sans CJK
SUBTITLE_FONT = (
    os.getenv("VC_SUBTITLE_FONT")
    or ("Microsoft YaHei" if os.name == "nt" else "Noto Sans CJK SC")
)
SUBTITLE_FONT_SIZE = int(os.getenv("VC_SUBTITLE_FONT_SIZE", "20"))

# ---------------------------------------------------------------- 输入

ALLOWED_VIDEO_EXT = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".mkv",
    ".avi",
    ".flv",
    ".ts",
    ".wmv",
}
MAX_UPLOAD_BYTES = int(os.getenv("VC_MAX_UPLOAD_MB", "4096")) * 1024 * 1024
