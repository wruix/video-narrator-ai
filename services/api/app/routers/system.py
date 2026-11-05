"""系统级接口：健康检查、模型目录、密钥管理、连接测试、用量统计。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import APP_NAME
from ..db import UsageRecord, get_db
from ..services import keyvault
from ai_providers import (
    TEXT_PROVIDERS,
    TTS_PROVIDERS,
    VISION_PROVIDERS,
    get_text,
    get_tts,
    get_vision,
    voice_catalog,
)
from media_core.config import ffmpeg_bin, ffprobe_bin

router = APIRouter()

STYLES = [
    {
        "id": "cinematic",
        "name": "电影感",
        "name_en": "Cinematic",
        "desc": "克制、有张力，像预告片旁白",
        "desc_en": "Restrained and dramatic, like a trailer voice-over",
        "sample": "灯光熄灭的那一刻，整个房间安静了下来。",
    },
    {
        "id": "story",
        "name": "故事叙述",
        "name_en": "Storytelling",
        "desc": "代入感强，讲述人物与事件",
        "desc_en": "Immersive, focused on people and events",
        "sample": "他推开那扇门的时候，屋里已经空了三年。",
    },
    {
        "id": "emotion",
        "name": "情绪叙事",
        "name_en": "Emotional",
        "desc": "重氛围与心理描写",
        "desc_en": "Atmosphere and inner world first",
        "sample": "有些告别，发生在对方还没转身的时候。",
    },
    {
        "id": "product",
        "name": "产品讲解",
        "name_en": "Product",
        "desc": "简洁专业，突出卖点",
        "desc_en": "Concise and professional, highlights key benefits",
        "sample": "一块屏幕，撑起了整套沉浸体验。",
    },
    {
        "id": "knowledge",
        "name": "知识科普",
        "name_en": "Explainer",
        "desc": "条理清晰，重解释",
        "desc_en": "Structured and explanatory",
        "sample": "真正决定精度的，是镜头背后那层算法。",
    },
    {
        "id": "documentary",
        "name": "纪录片旁白",
        "name_en": "Documentary",
        "desc": "客观克制，有历史纵深",
        "desc_en": "Objective narration with historical depth",
        "sample": "在这片荒原上，人类第一次留下了自己的痕迹。",
    },
]

ASPECTS = [
    {"id": "original", "name": "原始比例", "name_en": "Original"},
    {"id": "16:9", "name": "横屏 16:9", "name_en": "Landscape 16:9"},
    {"id": "9:16", "name": "竖屏 9:16", "name_en": "Portrait 9:16"},
    {"id": "1:1", "name": "方形 1:1", "name_en": "Square 1:1"},
    {"id": "4:5", "name": "竖版 4:5", "name_en": "Portrait 4:5"},
]

ASR_PROVIDERS = [
    {"id": "", "name": "不启用", "name_en": "Disabled"},
    {"id": "openai", "name": "Whisper API", "name_en": "Whisper API"},
    {"id": "local", "name": "本地 faster-whisper", "name_en": "Local faster-whisper"},
]

# 解说词语言（与界面语言相互独立）
NARRATION_LANGUAGES = [
    {"id": "zh-CN", "name": "中文（简体）", "name_en": "Chinese (Simplified)"},
    {"id": "zh-TW", "name": "中文（繁體）", "name_en": "Chinese (Traditional)"},
    {"id": "en-US", "name": "英语", "name_en": "English"},
    {"id": "en-GB", "name": "英语（英式）", "name_en": "English (UK)"},
    {"id": "ja-JP", "name": "日语", "name_en": "Japanese"},
    {"id": "ko-KR", "name": "韩语", "name_en": "Korean"},
    {"id": "es-ES", "name": "西班牙语", "name_en": "Spanish"},
    {"id": "fr-FR", "name": "法语", "name_en": "French"},
    {"id": "de-DE", "name": "德语", "name_en": "German"},
    {"id": "ru-RU", "name": "俄语", "name_en": "Russian"},
    {"id": "pt-BR", "name": "葡萄牙语", "name_en": "Portuguese"},
    {"id": "it-IT", "name": "意大利语", "name_en": "Italian"},
]

EMOTIONS = ["default", "平静", "紧张", "激昂", "悲伤", "欢快", "悬疑", "温情"]
EMOTIONS_EN = [
    "default",
    "calm",
    "tense",
    "passionate",
    "melancholy",
    "cheerful",
    "suspense",
    "warm",
]


# ---------------------------------------------------------------- 健康检查


@router.get("/health")
async def health():
    def probe():
        out = {}
        try:
            out["ffmpeg"] = ffmpeg_bin()
        except Exception as exc:  # noqa: BLE001
            out["ffmpeg"] = None
            out["ffmpeg_error"] = str(exc)
        try:
            out["ffprobe"] = ffprobe_bin()
        except Exception as exc:  # noqa: BLE001
            out["ffprobe"] = None
            out["ffprobe_error"] = str(exc)
        return out

    env = await asyncio.to_thread(probe)
    ok = bool(env.get("ffmpeg") and env.get("ffprobe"))
    return {
        # RA-34 F-2：应用身份字段。桌面端就绪检查据此确认监听端口的进程
        # 确实是本后端，而不是占用该端口的其他程序。
        "app": APP_NAME,
        "status": "ok" if ok else "degraded",
        "version": _version(),
        "ffmpeg": env.get("ffmpeg"),
        "ffprobe": env.get("ffprobe"),
        "ffmpeg_error": env.get("ffmpeg_error"),
        "ffprobe_error": env.get("ffprobe_error"),
    }


def _version() -> str:
    from ..config import APP_VERSION

    return APP_VERSION


# ---------------------------------------------------------------- 目录


@router.get("/providers")
def providers(db: Session = Depends(get_db)):
    vision = []
    for pid, provider in VISION_PROVIDERS.items():
        item = provider.spec.to_dict()
        item["capabilities"] = ["vision", "text"]
        key, source = keyvault.resolve_key(db, pid)
        item["key_present"] = bool(key)
        item["key_source"] = source
        item["key_masked"] = keyvault.mask_key(key)
        vision.append(item)

    text = []
    for pid, provider in TEXT_PROVIDERS.items():
        item = provider.spec.to_dict()
        item["capabilities"] = ["text"]
        key, source = keyvault.resolve_key(db, pid)
        item["key_present"] = bool(key)
        item["key_source"] = source
        item["key_masked"] = keyvault.mask_key(key)
        text.append(item)

    tts = []
    for pid, provider in TTS_PROVIDERS.items():
        item = provider.spec.to_dict()
        item["capabilities"] = ["tts"]
        key, source = keyvault.resolve_key(db, pid)
        item["key_present"] = bool(key)
        item["key_source"] = source
        item["key_masked"] = keyvault.mask_key(key)
        tts.append(item)

    return {
        "vision": vision,
        "text": text,
        "tts": tts,
        "voices": voice_catalog(),
        "styles": STYLES,
        "aspects": ASPECTS,
        "asr": ASR_PROVIDERS,
        "narration_languages": NARRATION_LANGUAGES,
        "emotions": EMOTIONS,
        "emotions_en": EMOTIONS_EN,
        "native_video": [p.spec.id for p in VISION_PROVIDERS.values() if p.spec.native_video],
    }


# ---------------------------------------------------------------- 密钥


class KeyPayload(BaseModel):
    provider: str
    key: str = ""
    scope: str = Field(default="user", pattern="^(user|server)$")


@router.get("/settings/keys")
def list_keys(db: Session = Depends(get_db)):
    items = []
    for pid in list(VISION_PROVIDERS) + list(TTS_PROVIDERS):
        info = keyvault.key_info(db, pid)
        items.append(
            {
                "provider": info.provider,
                "source": info.source,
                "present": info.present,
                "masked": info.masked,
            }
        )
    return {"keys": items, "prefer": keyvault.get_pref(db, "key_prefer", "user")}


@router.post("/settings/keys")
def upsert_key(payload: KeyPayload, db: Session = Depends(get_db)):
    if payload.scope == "server":
        keyvault.set_server_key(db, payload.provider, payload.key)
    else:
        keyvault.set_user_key(db, payload.provider, payload.key)
    return {"ok": True, "provider": payload.provider}


@router.delete("/settings/keys/{provider}")
def remove_key(provider: str, scope: str = "user", db: Session = Depends(get_db)):
    if scope == "server":
        keyvault.set_server_key(db, provider, "")
    else:
        keyvault.delete_user_key(db, provider)
    return {"ok": True}


class PreferPayload(BaseModel):
    prefer: str = Field(default="user", pattern="^(user|server)$")


@router.post("/settings/preferences")
def set_preferences(payload: PreferPayload, db: Session = Depends(get_db)):
    keyvault.set_pref(db, "key_prefer", payload.prefer)
    return {"ok": True, "prefer": payload.prefer}


# ---------------------------------------------------------------- 连接测试


class TestPayload(BaseModel):
    provider: str
    kind: str = Field(default="vision", pattern="^(vision|text|tts)$")


@router.post("/settings/test")
async def test_connection(payload: TestPayload, db: Session = Depends(get_db)):
    key, source = keyvault.resolve_key(db, payload.provider)
    if payload.kind == "tts":
        provider = get_tts(payload.provider)
    elif payload.kind == "text":
        provider = get_text(payload.provider)
    else:
        provider = get_vision(payload.provider)

    if provider.spec.requires_key and not key:
        raise HTTPException(status_code=400, detail=f"尚未配置 {provider.spec.name} 的密钥")

    try:
        result = await provider.test(key)
        return {"ok": True, "source": source, **result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "source": source, "message": str(exc)}


@router.get("/tiers")
def tiers():
    """当前生效的套餐与额度配置（来自 config/tiers.yaml，代码不写死数字）。"""
    from ..tiers import current_tier, load_tiers

    data = load_tiers().to_dict()
    data["active"] = current_tier().to_dict()
    return data


# ---------------------------------------------------------------- 用量


@router.get("/usage")
def usage(limit: int = 100, db: Session = Depends(get_db)):
    rows = (
        db.query(UsageRecord)
        .order_by(UsageRecord.id.desc())
        .limit(min(limit, 500))
        .all()
    )
    total_tokens = 0.0
    total_seconds = 0.0
    items = []
    for r in rows:
        if r.unit_name == "tokens":
            total_tokens += r.units or 0
        else:
            total_seconds += r.units or 0
        items.append(
            {
                "id": r.id,
                "project_id": r.project_id,
                "provider": r.provider,
                "model": r.model,
                "kind": r.kind,
                "units": r.units,
                "unit_name": r.unit_name,
                "note": r.note or "",
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return {
        "items": items,
        "total_tokens": round(total_tokens, 2),
        "total_seconds": round(total_seconds, 2),
    }
