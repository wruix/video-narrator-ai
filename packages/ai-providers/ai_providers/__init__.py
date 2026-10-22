"""Provider 注册表。

前端只通过这里枚举可用的模型服务，因此新增厂商 = 实现接口 + 在此注册。
"""

from __future__ import annotations

from .base import (
    AnalysisRequest,
    ProviderError,
    ProviderSpec,
    ShotDraft,
    TextRequest,
    Usage,
)
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider
from .qwen import QwenProvider
from .tts import (
    AzureTTSProvider,
    CustomTTSProvider,
    EdgeLiteProvider,
    EdgeTTSProvider,
    ElevenLabsProvider,
    OpenAITTSProvider,
    TTSProvider,
    voice_catalog,
)

# ---------------------------------------------------------------- 视觉 / 文本


def _build_vision_providers() -> dict[str, object]:
    gemini = GeminiProvider()
    openai = OpenAICompatProvider(
        provider_id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
        key_hint="OpenAI API Key",
        docs="https://platform.openai.com/docs/api-reference/chat",
        note="适合文案润色与结构化输出；视频需先抽帧",
    )
    doubao = OpenAICompatProvider(
        provider_id="doubao",
        name="豆包 / 火山方舟",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        default_model="doubao-seed-1-6-vision-250815",
        models=[
            "doubao-seed-1-6-vision-250815",
            "doubao-1-5-vision-32k-250315",
            "doubao-seed-1-6-250615",
        ],
        key_hint="火山方舟控制台创建 API Key（ark- 前缀）",
        docs="https://www.volcengine.com/docs/82379",
        note="中文视频理解与创作剪辑场景适配好",
    )
    silicon = OpenAICompatProvider(
        provider_id="siliconflow",
        name="硅基流动 SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        default_model="Qwen/Qwen2.5-VL-72B-Instruct",
        models=[
            "Qwen/Qwen2.5-VL-72B-Instruct",
            "Qwen/Qwen2.5-VL-7B-Instruct",
            "deepseek-ai/DeepSeek-V3",
        ],
        key_hint="SiliconFlow API Key",
        docs="https://docs.siliconflow.cn/",
    )
    ollama = OpenAICompatProvider(
        provider_id="ollama",
        name="本地模型（Ollama / vLLM）",
        base_url="http://localhost:11434/v1",
        default_model="qwen2.5vl:7b",
        models=["qwen2.5vl:7b", "qwen2.5vl:32b", "llama3.2-vision:11b", "minicpm-v"],
        requires_key=False,
        key_hint="通常无需 Key，本地服务自定",
        docs="https://github.com/ollama/ollama",
        note="离线内网部署首选，需自行准备显卡与服务",
    )
    return {
        "gemini": gemini,
        "openai": openai,
        "doubao": doubao,
        "qwen": QwenProvider(),
        "siliconflow": silicon,
        "ollama": ollama,
    }


def _build_text_providers() -> dict[str, object]:
    """文案优化模型：默认走 OpenAI 生态，但也允许用同一个模型做二次创作。"""
    providers = dict(_build_vision_providers())
    return providers


def _build_tts_providers() -> dict[str, TTSProvider]:
    return {
        "edge": EdgeTTSProvider(),
        "edge-lite": EdgeLiteProvider(),
        "openai-tts": OpenAITTSProvider(),
        "azure-tts": AzureTTSProvider(),
        "elevenlabs": ElevenLabsProvider(),
        "custom-tts": CustomTTSProvider(),
    }


VISION_PROVIDERS = _build_vision_providers()
TEXT_PROVIDERS = _build_text_providers()
TTS_PROVIDERS = _build_tts_providers()

# 支持原生视频上传的厂商（前端会给出提示）
NATIVE_VIDEO_PROVIDERS = [
    pid for pid, p in VISION_PROVIDERS.items() if getattr(p, "spec", None) and p.spec.native_video
]


def get_vision(provider_id: str):
    provider = VISION_PROVIDERS.get(provider_id)
    if provider is None:
        raise ProviderError(f"未知的视频理解模型：{provider_id}", provider=provider_id)
    return provider


def get_text(provider_id: str):
    provider = TEXT_PROVIDERS.get(provider_id)
    if provider is None:
        raise ProviderError(f"未知的文案模型：{provider_id}", provider=provider_id)
    return provider


def get_tts(provider_id: str) -> TTSProvider:
    provider = TTS_PROVIDERS.get(provider_id)
    if provider is None:
        raise ProviderError(f"未知的配音服务：{provider_id}", provider=provider_id)
    return provider


def provider_catalog() -> list[dict]:
    """前端「模型与创作设置」面板使用。"""
    items: list[dict] = []
    seen: set[str] = set()
    for pid, provider in VISION_PROVIDERS.items():
        spec: ProviderSpec = provider.spec
        d = spec.to_dict()
        d["capabilities"] = ["vision", "text"]
        items.append(d)
        seen.add(pid)
    for pid, provider in TTS_PROVIDERS.items():
        spec: ProviderSpec = provider.spec
        d = spec.to_dict()
        d["capabilities"] = ["tts"]
        items.append(d)
    return items


def vision_catalog() -> list[dict]:
    return [p.spec.to_dict() for p in VISION_PROVIDERS.values()]


def text_catalog() -> list[dict]:
    return [p.spec.to_dict() for p in TEXT_PROVIDERS.values()]


def tts_catalog() -> list[dict]:
    return [p.spec.to_dict() for p in TTS_PROVIDERS.values()]


__all__ = [
    "AnalysisRequest",
    "ProviderError",
    "ProviderSpec",
    "ShotDraft",
    "TextRequest",
    "Usage",
    "VISION_PROVIDERS",
    "TEXT_PROVIDERS",
    "TTS_PROVIDERS",
    "NATIVE_VIDEO_PROVIDERS",
    "get_vision",
    "get_text",
    "get_tts",
    "provider_catalog",
    "vision_catalog",
    "text_catalog",
    "tts_catalog",
    "voice_catalog",
]
