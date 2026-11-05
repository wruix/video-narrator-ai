"""全局配置：路径、运行时开关、默认值。

所有路径均可通过环境变量覆盖（.env 亦可），便于部署到不同的机器。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from media_core.config import (
    ALLOWED_VIDEO_EXT,
    BIN,
    DEFAULT_FRAME_INTERVAL,
    MAX_FRAMES_PER_SHOT,
    MAX_FRAMES_TOTAL,
    MAX_UPLOAD_BYTES,
    MOTION_THRESHOLD,
    SCENE_THRESHOLD,
    SUBTITLE_FONT,
    SUBTITLE_FONT_SIZE,
)

# 媒体相关常量由 media-core 定义，这里再导出，方便上层统一从 config 导入
__all__ = [
    "ALLOWED_VIDEO_EXT",
    "BIN",
    "DEFAULT_FRAME_INTERVAL",
    "MAX_FRAMES_PER_SHOT",
    "MAX_FRAMES_TOTAL",
    "MAX_UPLOAD_BYTES",
    "MOTION_THRESHOLD",
    "SCENE_THRESHOLD",
    "SUBTITLE_FONT",
    "SUBTITLE_FONT_SIZE",
]

# ---------------------------------------------------------------- 路径

# services/api/app/config.py -> services/api/app -> services/api -> <repo>
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

# RA-34 F-3：冻结（PyInstaller）模式下 __file__ 位于临时解包目录，
# ROOT_DIR/data 既不可控也不持久。冻结模式必须显式注入 VC_DATA_DIR，
# 缺失立即失败，不允许静默回退（实证：RA-33 候选包无法写入用户数据）。
FROZEN = bool(getattr(sys, "frozen", False))

_ENV_DATA_DIR = os.getenv("VC_DATA_DIR")
if FROZEN and not _ENV_DATA_DIR:
    raise SystemExit(
        "VC_DATA_DIR is required in frozen (packaged) mode: refusing to fall back "
        f"to the temporary bundle dir ({ROOT_DIR / 'data'}). "
        "The desktop launcher must inject a persistent per-user data directory."
    )
DATA_DIR = Path(_ENV_DATA_DIR or (ROOT_DIR / "data")).resolve()

UPLOAD_DIR = DATA_DIR / "uploads"
WORK_DIR = DATA_DIR / "work"
OUTPUT_DIR = DATA_DIR / "output"
FRAME_DIR = WORK_DIR / "frames"
AUDIO_DIR = WORK_DIR / "audio"
TTS_DIR = WORK_DIR / "tts"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "station.db"
MASTER_KEY_PATH = DATA_DIR / "master.key"

# ---------------------------------------------------------------- 网络


@dataclass
class NetConfig:
    connect_timeout: float = 30.0
    read_timeout: float = 600.0
    upload_timeout: float = 1800.0
    max_retries: int = 3
    retry_backoff: float = 2.0

    @classmethod
    def from_env(cls) -> "NetConfig":
        return cls(
            connect_timeout=float(os.getenv("VC_CONNECT_TIMEOUT", "30")),
            read_timeout=float(os.getenv("VC_READ_TIMEOUT", "600")),
            upload_timeout=float(os.getenv("VC_UPLOAD_TIMEOUT", "1800")),
            max_retries=int(os.getenv("VC_MAX_RETRIES", "3")),
            retry_backoff=float(os.getenv("VC_RETRY_BACKOFF", "2")),
        )


NET = NetConfig.from_env()



def ensure_dirs() -> None:
    for d in (
        DATA_DIR,
        UPLOAD_DIR,
        WORK_DIR,
        OUTPUT_DIR,
        FRAME_DIR,
        AUDIO_DIR,
        TTS_DIR,
        LOG_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- 运行参数

APP_NAME = "VideoNarrator AI"
APP_VERSION = "1.0.0"
API_PREFIX = "/api"


# 服务端统一托管的 Key（模式 B）
# 约定：环境变量 VC_SERVER_KEY_<PROVIDER> 存在时，该 provider 使用系统 Key。
SERVER_KEY_ENV_PREFIX = "VC_SERVER_KEY_"


def server_key_env_name(provider: str) -> str:
    return f"{SERVER_KEY_ENV_PREFIX}{provider.upper().replace('-', '_')}"


def server_key_from_env(provider: str) -> str | None:
    val = os.getenv(server_key_env_name(provider))
    return val.strip() if val and val.strip() else None


# ---------------------------------------------------------------- 安全


def master_key_material() -> bytes:
    """返回用于派生加密密钥的原始材料。

    优先使用环境变量 VC_MASTER_KEY；否则在数据目录生成一个随机文件。
    """
    env = os.getenv("VC_MASTER_KEY")
    if env:
        return env.encode("utf-8")
    ensure_dirs()
    if not MASTER_KEY_PATH.exists():
        import secrets

        MASTER_KEY_PATH.write_bytes(secrets.token_bytes(32))
        try:
            os.chmod(MASTER_KEY_PATH, 0o600)
        except OSError:
            pass
    return MASTER_KEY_PATH.read_bytes()
