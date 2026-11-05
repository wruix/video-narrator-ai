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

    # RA-34 F-1：冻结产物关键模块导入硬门禁。
    # PyInstaller 对缺失 hiddenimport 只告警不报错，曾产出缺 media_core 的残包
    # （Run 41384939572，RA-33 实证启动即崩）。这里在监听前显式导入，缺失则
    # 非零退出并打印可诊断信息，让 CI 自检与用户都能看到明确失败。
    try:
        import ai_providers  # noqa: F401
        import media_core  # noqa: F401
        import media_core.config  # noqa: F401
        import ai_providers.base  # noqa: F401
    except ImportError as exc:
        print(f"FATAL: frozen backend missing required module: {exc}", file=sys.stderr)
        print(f"sys.path={sys.path}", file=sys.stderr)
        raise SystemExit(2)

    import uvicorn

    from app.main import app

    port = int(os.getenv("VNS_PORT", "8080"))
    host = os.getenv("VNS_HOST", "127.0.0.1")
    # RA-34 F-2：端口冲突硬失败。Electron 侧已先探测端口；若仍被占用，
    # 静默失败或降级会让 Electron 把别的程序响应误当本应用 Ready。
    # 注意：此处绝不可设 SO_REUSEADDR —— Windows 上该选项会让 bind() 在端口
    # 已被监听时依然成功（RA-34 本地 smoke 实证：带 REUSEADDR 预检漏检，
    # 直到 uvicorn 绑定才以 WinError 10048 失败）。不带该选项时 bind() 与
    # uvicorn（Windows 下不设 REUSEADDR）的绑定语义一致，冲突即时暴露。
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as exc:
        print(f"FATAL: cannot bind {host}:{port} (VNS_PORT): {exc}", file=sys.stderr)
        raise SystemExit(4)
    finally:
        probe.close()

    uvicorn.run(app, host=host, port=port, log_level="info")
