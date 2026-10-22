"""可选的访问鉴权。

默认不启用（本机单用户使用）。一旦设置环境变量，以下任意一种方式都可携带凭证：

  * 请求头 ``Authorization: Bearer <token>``
  * 请求头 ``X-Access-Token: <token>``
  * 查询参数 ``?token=<token>``（用于浏览器直接打开视频/成片链接）
  * Cookie ``vns_token=<token>``

前端在「设置」里填写访问口令后存入 localStorage，由 API 客户端自动带上。
"""

from __future__ import annotations

import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse

TOKEN_ENV = "VC_ACCESS_TOKEN"
COOKIE_NAME = "vns_token"
HEADER_NAME = "X-Access-Token"

# 这些路径不需要凭证，方便健康检查与首次打开页面
PUBLIC_PATHS = {
    "/api/ping",
    "/api/health",
    "/favicon.ico",
}


def access_token() -> str:
    return (os.getenv(TOKEN_ENV) or "").strip()


def auth_enabled() -> bool:
    return bool(access_token())


def _extract(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    header = request.headers.get(HEADER_NAME, "")
    if header:
        return header.strip()
    token = request.query_params.get("token", "")
    if token:
        return token.strip()
    return request.cookies.get(COOKIE_NAME, "") or ""


def verify(request: Request) -> bool:
    """校验请求凭证；未启用鉴权时一律放行。"""
    expected = access_token()
    if not expected:
        return True
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/assets/") or path == "/":
        return True
    provided = _extract(request)
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


async def auth_middleware(request: Request, call_next):
    if not auth_enabled() or verify(request):
        return await call_next(request)
    return JSONResponse(
        status_code=401,
        content={
            "detail": "需要访问口令：请在「设置」中填写，或使用 Authorization: Bearer <token> 头",
            "code": "access_token_required",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )
