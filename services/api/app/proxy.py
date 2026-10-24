"""系统代理探测与启用。

背景：在很多网络环境下，模型 API 必须经过本地代理（VPN/机场客户端等）。
httpx 只认 ``HTTP_PROXY`` / ``HTTPS_PROXY`` 环境变量，但用户往往只在
Windows「设置 → 网络和 Internet → 代理」里配置了系统代理，注册表有、
环境变量没有，于是表现为「连接超时 / All connection attempts failed」。

这里在应用启动时按以下顺序解析代理：

1. 环境变量 ``VC_PROXY``（最高优先级，显式指定）
2. 环境变量 ``HTTP_PROXY`` / ``HTTPS_PROXY``（用户已按标准方式设置）
3. Windows 注册表中的 WinINET 系统代理（自动发现）
4. macOS / Linux 的常见环境变量（由 httpx 自行处理）

解析成功后写入进程环境变量，httpx 的 ``trust_env=True`` 会自动使用。
"""

from __future__ import annotations

import logging
import os
import sys
from urllib.parse import urlparse

logger = logging.getLogger("app.proxy")


def _from_registry() -> str | None:
    """读取 Windows WinINET 系统代理（Internet Settings）。"""
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return None
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
    except OSError:
        return None
    try:
        enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
        if not enabled:
            return None
        server, _ = winreg.QueryValueEx(key, "ProxyServer")
    except OSError:
        return None
    finally:
        try:
            winreg.CloseKey(key)
        except OSError:
            pass
    if not server:
        return None
    server = server.strip()
    # ProxyServer 可能是 "host:port" 或 "http=host:port;https=host:port"
    # 统一只返回地址部分，协议前缀交给 _normalize 补全
    if "=" in server:
        for part in server.split(";"):
            scheme, _, addr = part.partition("=")
            if scheme.strip().lower() in ("http", "https"):
                return addr.strip()
        return None
    return server


def _normalize(url: str) -> str | None:
    url = url.strip()
    if not url:
        return None
    if "://" not in url:
        url = f"http://{url}"
    parsed = urlparse(url)
    if not parsed.hostname:
        return None
    return url


def detect_proxy() -> tuple[str | None, str]:
    """返回 (代理地址, 来源说明)。"""
    explicit = os.getenv("VC_PROXY")
    if explicit:
        url = _normalize(explicit)
        if url:
            return url, "VC_PROXY"

    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.getenv(var)
        if value:
            url = _normalize(value)
            if url:
                return url, var

    reg = _normalize(_from_registry() or "")
    if reg:
        return reg, "Windows 系统代理"

    return None, "未配置"


def apply_proxy() -> str | None:
    """把探测到的代理写入环境变量，供 httpx 使用。返回实际生效的地址。"""
    url, source = detect_proxy()
    if not url:
        logger.info("未检测到代理，模型请求将直连")
        return None

    # 已经由环境变量指定过，尊重用户原有设置，不覆盖
    if source.startswith(("HTTP", "http")) and os.getenv("VC_PROXY") is None:
        logger.info("使用已有代理环境变量：%s", url)
        return url

    os.environ["HTTP_PROXY"] = url
    os.environ["HTTPS_PROXY"] = url
    os.environ.setdefault("http_proxy", url)
    os.environ.setdefault("https_proxy", url)
    # 本地 Ollama / OpenAI 兼容端点不应走代理
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost,::1")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost,::1")
    logger.info("已启用代理（来源：%s）：%s", source, url)
    return url


def proxy_status() -> dict:
    url, source = detect_proxy()
    return {
        "proxy": url,
        "source": source,
        "enabled": bool(url),
        "platform": sys.platform,
    }
