"""media-core 的运行配置。

这些参数只跟「本机媒体处理」有关，因此放在可复用包里，
API 服务与 Worker 都会引用同一份定义。
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Binaries:
    """FFmpeg / FFprobe 可执行文件定位。

    查找优先级：
    1. 环境变量 VC_FFMPEG / VC_FFPROBE（用户显式配置）
    2. 应用随包携带的工具（PyInstaller / Electron 打包后的 resources 目录）
    3. 系统 PATH
    """

    ffmpeg: str = field(default_factory=lambda: os.getenv("VC_FFMPEG", "").strip())
    ffprobe: str = field(default_factory=lambda: os.getenv("VC_FFPROBE", "").strip())

    def __post_init__(self) -> None:
        # 去除可能的引号
        if self.ffmpeg:
            self.ffmpeg = self.ffmpeg.strip('"').strip("'")
        if self.ffprobe:
            self.ffprobe = self.ffprobe.strip('"').strip("'")

    def _resolve_one(self, which: str, env_name: str, binary_name: str) -> str | None:
        """按优先级解析单个可执行文件路径。"""
        # 1. 用户显式配置
        env_val = os.getenv(env_name)
        if env_val:
            env_val = env_val.strip().strip('"').strip("'")
            if env_val and Path(env_val).exists():
                return env_val

        # 2. 应用随包携带的工具（PyInstaller / Electron 打包后）
        # sys.executable 所在目录通常和随包资源在同一层
        bundled = Path(sys.executable).parent / binary_name
        if bundled.exists():
            return str(bundled)

        # 开发环境：源码目录下的 bin/ 目录
        dev_rel = Path(__file__).resolve().parent.parent / "bin" / binary_name
        if dev_rel.exists():
            return str(dev_rel)

        # 3. 系统 PATH
        found = shutil.which(binary_name)
        if found:
            return found

        # 4. 常见安装路径（Windows / Linux / macOS）
        common = [
            Path("C:/ffmpeg/bin") / binary_name,
            Path("C:/Program Files/ffmpeg/bin") / binary_name,
            Path("/usr/bin") / binary_name,
            Path("/usr/local/bin") / binary_name,
            Path("/opt/homebrew/bin") / binary_name,
        ]
        for p in common:
            if p.exists():
                return str(p)

        return None

    def resolve(self, which: str) -> str | None:
        if which == "ffmpeg":
            binary_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            return self._resolve_one("ffmpeg", "VC_FFMPEG", binary_name)
        if which == "ffprobe":
            binary_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
            return self._resolve_one("ffprobe", "VC_FFPROBE", binary_name)
        return None

    def resolve_or_raise(self, which: str) -> str:
        """解析并返回可执行文件路径，找不到时抛出 MediaError。"""
        exe = self.resolve(which)
        if exe:
            return exe
        name = which
        env_name = f"VC_{which.upper()}"
        binary_name = f"{which}.exe" if os.name == "nt" else which
        raise MediaError(
            f"未找到 {name}。请安装 {name} 并加入 PATH，"
            f"或通过环境变量 {env_name} 指向可执行文件路径。"
        )


BIN = Binaries()


def ffmpeg_bin() -> str:
    """返回 ffmpeg 可执行文件路径，找不到时抛出 MediaError。"""
    return BIN.resolve_or_raise("ffmpeg")


def ffprobe_bin() -> str:
    """返回 ffprobe 可执行文件路径，找不到时抛出 MediaError。"""
    return BIN.resolve_or_raise("ffprobe")


class MediaError(RuntimeError):
    """媒体处理基础异常。"""


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