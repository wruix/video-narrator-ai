"""API Key 的加密存储与解析。

设计要点：
- 密钥永远不通过接口明文返回前端，只返回掩码与是否存在。
- 用户自带的 Key（模式 A）与平台托管 Key（模式 B）分表存放，互不覆盖。
- 落盘使用 Fernet 对称加密，主密钥来自环境变量或本地 data/master.key。
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken

from .config import master_key_material, server_key_from_env

KeyScope = Literal["user", "server"]


def _build_cipher() -> Fernet:
    raw = master_key_material()
    digest = hashlib.sha256(raw).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


_CIPHER = _build_cipher()


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        raise ValueError("plaintext required")
    return _CIPHER.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    try:
        return _CIPHER.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:  # pragma: no cover - 数据损坏路径
        raise ValueError("无法解密存储的密钥，可能主密钥已变更") from exc


def mask_key(key: str | None) -> str:
    """生成用于前端展示的掩码，例如 sk-abc...xyz。"""
    if not key:
        return ""
    key = key.strip()
    if len(key) <= 10:
        return "*" * len(key)
    head = key[:4]
    tail = key[-4:]
    return f"{head}{'*' * 6}{tail}"


@dataclass
class ResolvedKey:
    key: str | None
    source: str  # "user" | "server" | "none"


def resolve_server_key(provider: str) -> ResolvedKey:
    """解析平台托管的 Key（模式 B）。"""
    val = server_key_from_env(provider)
    if val:
        return ResolvedKey(val, "server")
    return ResolvedKey(None, "none")
