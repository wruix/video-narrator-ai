# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 规格：把 FastAPI 后端打成桌面包里的独立可执行文件。

产物： services/api/dist/server/vns-server(.exe)
"""

import sys  # noqa: E402
from pathlib import Path

REPO_ROOT = Path(SPECPATH).parent.parent.parent  # noqa: F821

datas = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "edge_tts",
    "ai_providers",
    "media_core",
]

# 打包进前端静态资源（存在才带）
web_dist = REPO_ROOT / "apps" / "web" / "dist"
if web_dist.exists():
    datas.append((str(web_dist), "web/dist"))

# FFmpeg/FFprobe 不再由 PyInstaller 打包进 vns-server。
# 它们作为独立资源由 Electron Builder 从 services/api/ffmpeg-bin/ 分发进 resources/server/，
# 后端通过 Electron 主进程传入的 VC_FFMPEG / VC_FFPROBE 环境变量定位（见 apps/desktop/src/backend.ts）。
# 这样 PyInstaller 产物目录（dist/server）只包含 vns-server 本身，不与 FFmpeg 输入耦合，
# 也避免 FFmpeg 被重复嵌入（既编译进 EXE，又作为独立文件拷贝）。

a = Analysis(  # noqa: F821
    ["build_server.py"],
    pathex=[
        str(Path(SPECPATH).parent),
        str(REPO_ROOT / "packages" / "media-core"),
        str(REPO_ROOT / "packages" / "ai-providers"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="vns-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
