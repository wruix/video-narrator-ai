"""PyInstaller 打包入口。

桌面端安装包会把本文件编译成独立的 ``vns-server`` 可执行文件，
终端用户因此不需要自己安装 Python。

用法：
    pyinstaller --clean services/api/build_server.py
"""

from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path

# 打包时把仓库内的两个 Python 包一起收进去
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for extra in (REPO_ROOT / "packages" / "media-core", REPO_ROOT / "packages" / "ai-providers"):
    if extra.exists():
        sys.path.insert(0, str(extra))

if __name__ == "__main__":
    multiprocessing.freeze_support()

    import uvicorn

    from app.main import app

    port = int(os.getenv("VNS_PORT", "8080"))
    host = os.getenv("VNS_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, log_level="info")
