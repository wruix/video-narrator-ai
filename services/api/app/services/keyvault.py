"""API Key 仓库：模式 A（用户自带）与模式 B（平台托管）统一入口。

解析优先级：用户级 Key > 平台托管 Key > 环境变量。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..db import Setting
from ..security import decrypt, encrypt, mask_key, resolve_server_key

USER_KEY_PREFIX = "apikey:user:"
SERVER_KEY_PREFIX = "apikey:server:"


@dataclass
class KeyInfo:
    provider: str
    source: str  # user | server | none
    masked: str
    present: bool


def _key_from_db(db: Session, key: str) -> str | None:
    row = db.get(Setting, key)
    if not row or not row.value:
        return None
    try:
        return decrypt(row.value)
    except ValueError:
        return None


def set_user_key(db: Session, provider: str, value: str) -> None:
    value = value.strip()
    row = db.get(Setting, USER_KEY_PREFIX + provider)
    if not value:
        if row:
            db.delete(row)
        db.commit()
        return
    if row:
        row.value = encrypt(value)
    else:
        db.add(Setting(key=USER_KEY_PREFIX + provider, value=encrypt(value), is_secret=True))
    db.commit()


def set_server_key(db: Session, provider: str, value: str) -> None:
    """平台侧保存统一托管的 Key（模式 B）。"""
    value = value.strip()
    row = db.get(Setting, SERVER_KEY_PREFIX + provider)
    if not value:
        if row:
            db.delete(row)
        db.commit()
        return
    if row:
        row.value = encrypt(value)
    else:
        db.add(Setting(key=SERVER_KEY_PREFIX + provider, value=encrypt(value), is_secret=True))
    db.commit()


def delete_user_key(db: Session, provider: str) -> None:
    set_user_key(db, provider, "")


def resolve_key(db: Session, provider: str, prefer: str = "user") -> tuple[str | None, str]:
    """返回 (key, source)。prefer='user' 时优先使用用户自有 Key。"""
    if prefer != "server":
        user_key = _key_from_db(db, USER_KEY_PREFIX + provider)
        if user_key:
            return user_key, "user"
    server_key = _key_from_db(db, SERVER_KEY_PREFIX + provider)
    if server_key:
        return server_key, "server"
    env = resolve_server_key(provider)
    if env.key:
        return env.key, "server"
    return None, "none"


def key_info(db: Session, provider: str) -> KeyInfo:
    key, source = resolve_key(db, provider)
    return KeyInfo(
        provider=provider,
        source=source,
        masked=mask_key(key),
        present=bool(key),
    )


def all_key_info(db: Session, providers: list[str]) -> list[KeyInfo]:
    return [key_info(db, p) for p in providers]


def get_pref(db: Session, key: str, default: str = "user") -> str:
    row = db.get(Setting, f"pref:{key}")
    if row and row.value:
        try:
            return decrypt(row.value)
        except ValueError:
            return default
    return default


def set_pref(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, f"pref:{key}")
    if row:
        row.value = encrypt(value)
    else:
        db.add(Setting(key=f"pref:{key}", value=encrypt(value), is_secret=True))
    db.commit()


def list_user_providers(db: Session) -> list[str]:
    from sqlalchemy import select

    stmt = select(Setting.key).where(Setting.key.startswith(USER_KEY_PREFIX))
    return [k[len(USER_KEY_PREFIX) :] for k in db.scalars(stmt)]
