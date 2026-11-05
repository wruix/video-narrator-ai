"""FastAPI 应用入口。"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import auth_middleware
from .config import API_PREFIX, APP_NAME, APP_VERSION, LOG_DIR, ROOT_DIR, ensure_dirs
from .db import init_db
from .logging_setup import setup_logging
from .routers import projects, system
from .services.jobs import manager

setup_logging()
logger = logging.getLogger("app")

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Multi-model AI video narration workstation",
)

# Ollama 本地模型：与 OpenAI 兼容 provider 并存，走 /api/chat 原生协议
from ai_providers import VISION_PROVIDERS, TEXT_PROVIDERS  # noqa: E402
from .services import ollama_provider as _ollama  # noqa: E402

# CORS：默认允许同源访问；部署到公网时建议在 .env 里收紧
_cors_origins = [
    o.strip() for o in (os.getenv("VC_CORS_ORIGINS") or "").split(",") if o.strip()
] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(auth_middleware)


@app.on_event("startup")
async def on_startup() -> None:
    ensure_dirs()
    init_db()
    # 自动发现系统代理（Windows 代理客户端等），否则模型 API 会连接超时
    from .proxy import apply_proxy

    apply_proxy()
    manager.attach_loop(asyncio.get_running_loop())
    manager.recover_interrupted()
    # Ollama 本地模型：与包里的 OpenAI 兼容 provider 并存，走 /api/chat 原生协议
    from .services import ollama_provider as _ollama  # noqa: E402

    VISION_PROVIDERS["ollama"] = _ollama.OllamaProvider()
    TEXT_PROVIDERS["ollama"] = _ollama.OllamaProvider()
    logger.info("%s v%s 已启动", APP_NAME, APP_VERSION)


@app.get(f"{API_PREFIX}/proxy")
def proxy_status():
    """当前代理状态（用于排查「连不上模型服务」）。"""
    from .proxy import proxy_status as _status

    return _status()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """统一异常出口：记录完整堆栈，并向调用方返回可读的错误信息。"""
    logger.error(
        "未处理异常 %s %s -> %s\n%s",
        request.method,
        request.url.path,
        exc,
        traceback.format_exc(),
    )
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "errors.log").open("a", encoding="utf-8") as fh:
            fh.write(f"--- {request.method} {request.url.path}\n")
            fh.write(traceback.format_exc())
            fh.write("\n")
    except OSError:
        pass
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}", "log": str(LOG_DIR / "errors.log")},
    )


@app.get(f"{API_PREFIX}/ping")
def ping():
    return {"ok": True, "app": APP_NAME, "version": APP_VERSION}


app.include_router(system.router, prefix=API_PREFIX)
app.include_router(projects.router, prefix=API_PREFIX)

# ---------------------------------------------------------------- 前端静态资源


def _find_frontend_dist() -> Path | None:
    """定位前端构建产物。

    RA-34 F-3：冻结（打包）模式与开发模式严格分离：
      * 冻结模式：只认 VC_FRONTEND_DIST 注入或随包 web/dist（PyInstaller datas），
        绝不回退到开发目录（开发目录在用户机器上不存在且可能指向陈旧前端）。
        两者皆无 -> None，由 missing_frontend 分支给出明确 404（可诊断）。
      * 开发模式：保持原逻辑（环境变量 -> monorepo 约定位置）。
    """
    env = os.getenv("VC_FRONTEND_DIST")
    if env:
        p = Path(env)
        return p if p.exists() else None

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass) / "web" / "dist"
            return bundled if bundled.exists() else None
        return None

    for candidate in (
        ROOT_DIR / "apps" / "web" / "dist",
        ROOT_DIR / "frontend" / "dist",
    ):
        if candidate.exists():
            return candidate
    return None


FRONTEND_DIST = _find_frontend_dist()

if FRONTEND_DIST and FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith(API_PREFIX):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse({"detail": "前端尚未构建"}, status_code=404)
else:

    @app.get("/{full_path:path}")
    def missing_frontend(full_path: str):
        if full_path.startswith(API_PREFIX):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return JSONResponse(
            {
                "detail": "前端尚未构建，请先执行 scripts\\setup.ps1 或 npm run build",
                "expected": str(FRONTEND_DIST),
            },
            status_code=404,
        )
