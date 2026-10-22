"""AI 配音（TTS）适配器。

可替换的配音服务：
  * edge      — Microsoft Edge 语音，免费、中文音色丰富（默认）
  * openai    — OpenAI /audio/speech 或任意 OpenAI 兼容网关
  * azure     — Azure Cognitive Services Speech
  * elevenlabs— ElevenLabs
  * custom    — 自定义 HTTP 端点（POST {text, voice, ...} → 音频）
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


from .base import ProviderError, ProviderSpec, Usage, http_client

# ---------------------------------------------------------------- 音色目录


@dataclass
class Voice:
    id: str
    name: str
    gender: str
    tone: str
    provider: str = "edge"
    tags: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "tone": self.tone,
            "provider": self.provider,
            "tags": self.tags or [],
        }


EDGE_VOICES: list[Voice] = [
    Voice("zh-CN-XiaoxiaoNeural", "晓晓", "女", "自然亲和", tags=["通用", "解说"]),
    Voice("zh-CN-YunxiNeural", "云希", "男", "阳光清朗", tags=["通用", "解说"]),
    Voice("zh-CN-YunjianNeural", "云健", "男", "浑厚有力", tags=["旁白", "激昂"]),
    Voice("zh-CN-XiaoyiNeural", "晓伊", "女", "活泼明快", tags=["欢快", "产品"]),
    Voice("zh-CN-YunyangNeural", "云扬", "男", "专业播报", tags=["播报", "纪录片"]),
    Voice("zh-CN-XiaochenNeural", "晓辰", "女", "沉稳冷静", tags=["悬疑", "情绪"]),
    Voice("zh-CN-XiaohanNeural", "晓涵", "女", "温柔细腻", tags=["温情", "故事"]),
    Voice("zh-CN-XiaomoNeural", "晓墨", "女", "叙述感强", tags=["故事", "叙述"]),
    Voice("zh-CN-XiaoruiNeural", "晓睿", "女", "青年女声", tags=["通用"]),
    Voice("zh-CN-XiaoshuangNeural", "晓双", "女", "儿童音", tags=["轻松"]),
    Voice("zh-CN-XiaoxuanNeural", "晓萱", "女", "成熟女声", tags=["情绪"]),
    Voice("zh-CN-XiaoyanNeural", "晓颜", "女", "标准女声", tags=["播报"]),
    Voice("zh-CN-XiaoyiNeural-lite", "晓伊（极速）", "女", "轻量", provider="edge-lite"),
    Voice("zh-CN-YunxiNeural-lite", "云希（极速）", "男", "轻量", provider="edge-lite"),
    Voice("en-US-AriaNeural", "Aria", "女", "英文自然", tags=["English"]),
    Voice("en-US-GuyNeural", "Guy", "男", "英文沉稳", tags=["English"]),
    Voice("ja-JP-NanamiNeural", "七海", "女", "日语", tags=["日本語"]),
    Voice("ko-KR-SunHiNeural", "善熙", "女", "韩语", tags=["한국어"]),
]


def voice_catalog() -> list[dict]:
    return [v.to_dict() for v in EDGE_VOICES]


# ---------------------------------------------------------------- 抽象


class TTSProvider:
    id = "tts"
    spec: ProviderSpec

    async def synthesize(
        self, *, text: str, voice: str, speed: str, emotion: str, out_path: Path, key: str = ""
    ) -> Usage:
        raise NotImplementedError

    async def test(self, key: str) -> dict:
        raise NotImplementedError

    @staticmethod
    def _speed_delta(speed: str) -> float:
        """'+10%' -> 1.10 ; '-5%' -> 0.95 ; '+0%' -> 1.0"""
        if not speed:
            return 1.0
        s = speed.strip().replace("%", "")
        try:
            val = float(s)
        except ValueError:
            return 1.0
        return max(0.5, min(2.0, 1.0 + val / 100.0))


# ---------------------------------------------------------------- Edge


class EdgeTTSProvider(TTSProvider):
    id = "edge"

    def __init__(self, provider_id: str = "edge", name: str = "Microsoft Edge 语音（免费）"):
        self.spec = ProviderSpec(
            id=provider_id,
            name=name,
            kind="tts",
            default_model="edge-tts",
            models=["edge-tts"],
            requires_key=False,
            key_hint="无需 API Key",
            note="免费且离线音色多，适合快速试听；正式商用请确认微软许可条款",
        )

    async def synthesize(
        self, *, text: str, voice: str, speed: str, emotion: str, out_path: Path, key: str = ""
    ) -> Usage:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "缺少 edge-tts 依赖，请执行 pip install edge-tts", provider=self.id
            ) from exc

        rate = f"{int(round((self._speed_delta(speed) - 1) * 100)):+d}%"
        pitch = _emotion_pitch(emotion)
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(str(out_path))
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise ProviderError("配音合成失败：未产生音频", provider=self.id)
        return Usage(self.id, "edge-tts", "tts", _duration_of(out_path), "seconds")

    async def test(self, key: str) -> dict:
        return {"ok": True, "message": "Edge 配音无需密钥，可直接使用"}


class EdgeLiteProvider(EdgeTTSProvider):
    def __init__(self):
        super().__init__(provider_id="edge-lite", name="Microsoft Edge 语音 · 极速版")


def _emotion_pitch(emotion: str) -> str:
    mapping = {
        "default": "+0Hz",
        "平静": "+0Hz",
        "紧张": "+0Hz",
        "激昂": "+8Hz",
        "悲伤": "-8Hz",
        "欢快": "+10Hz",
        "悬疑": "-4Hz",
        "温情": "+2Hz",
    }
    return mapping.get(emotion, "+0Hz")


# ---------------------------------------------------------------- OpenAI 兼容


class OpenAITTSProvider(TTSProvider):
    id = "openai-tts"

    def __init__(self, base_url: str = "https://api.openai.com/v1"):
        self.base_url = base_url.rstrip("/")
        self.spec = ProviderSpec(
            id=self.id,
            name="OpenAI 语音合成",
            kind="tts",
            default_model="gpt-4o-mini-tts",
            models=["gpt-4o-mini-tts", "tts-1", "tts-1-hd"],
            requires_key=True,
            key_hint="OpenAI API Key（OpenAI 平台创建）",
            docs="https://platform.openai.com/docs/api-reference/audio/createSpeech",
        )

    async def synthesize(
        self, *, text: str, voice: str, speed: str, emotion: str, out_path: Path, key: str = ""
    ) -> Usage:
        payload = {
            "model": self.spec.default_model,
            "voice": voice or "alloy",
            "input": text,
            "response_format": "mp3",
            "speed": round(self._speed_delta(speed), 2),
        }
        return await _synthesize_openai(
            base_url=self.base_url,
            key=key,
            payload=payload,
            out_path=out_path,
            provider_id=self.id,
        )

    async def test(self, key: str) -> dict:
        payload = {
            "model": self.spec.default_model,
            "voice": "alloy",
            "input": "测试",
            "response_format": "mp3",
        }
        async with http_client(60.0) as client:
            resp = await client.post(
                f"{self.base_url}/audio/speech",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            )
        if resp.status_code >= 300:
            raise ProviderError(f"OpenAI 配音失败（{resp.status_code}）：{resp.text[:300]}", provider=self.id)
        return {"ok": True, "message": "OpenAI 配音连接正常"}


async def _synthesize_openai(
    *, base_url: str, key: str, payload: dict, out_path: Path, provider_id: str
) -> Usage:
    async with http_client(300) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/audio/speech",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
    if resp.status_code >= 300:
        raise ProviderError(
            f"配音合成失败（{resp.status_code}）：{resp.text[:300]}", provider=provider_id
        )
    out_path.write_bytes(resp.content)
    return Usage(provider_id, payload.get("model", ""), "tts", _duration_of(out_path), "seconds")


# ---------------------------------------------------------------- Azure


class AzureTTSProvider(TTSProvider):
    id = "azure-tts"

    def __init__(self):
        self.spec = ProviderSpec(
            id=self.id,
            name="Azure 语音服务",
            kind="tts",
            default_model="zh-CN-XiaoxiaoNeural",
            models=["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-YunjianNeural"],
            requires_key=True,
            key_hint="需要 Speech Key 与 Region，例如 eastasia",
            docs="https://learn.microsoft.com/azure/ai-services/speech-service/",
        )

    async def synthesize(
        self, *, text: str, voice: str, speed: str, emotion: str, out_path: Path, key: str = ""
    ) -> Usage:
        k, region = _split_azure_creds(key)
        if not key or not region:
            raise ProviderError("Azure 配音需要「Key|Region」格式的凭证", provider=self.id)
        import ssl

        url = (
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
            f"?language=zh-CN&name={voice or self.spec.default_model}"
            f"&rate={int(round((self._speed_delta(speed) - 1) * 100))}%25"
        )
        body = (
            "<speak version='1.0' xml:lang='zh-CN'>"
            f"<voice name='{voice or self.spec.default_model}'>"
            f"<prosody rate='{int(round((self._speed_delta(speed) - 1) * 100))}%'>"
            f"{_xml_escape(text)}</prosody></voice></speak>"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": k,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "video-narration-station",
        }
        async with http_client(300, verify=ssl.create_default_context()) as client:
            resp = await client.post(url, headers=headers, content=body.encode("utf-8"))
        if resp.status_code >= 300:
            raise ProviderError(
                f"Azure 配音失败（{resp.status_code}）：{resp.text[:300]}", provider=self.id
            )
        out_path.write_bytes(resp.content)
        return Usage(self.id, voice, "tts", _duration_of(out_path), "seconds")

    async def test(self, key: str) -> dict:
        k, region = _split_azure_creds(key)
        if not k or not region:
            return {"ok": False, "message": "凭证格式应为「Key|Region」"}
        return {"ok": True, "message": f"凭证格式正确，Region={region}"}


def _split_azure_creds(raw: str) -> tuple[str, str]:
    if "|" in raw:
        k, _, r = raw.partition("|")
        return k.strip(), r.strip()
    return raw.strip(), ""


# ---------------------------------------------------------------- ElevenLabs


class ElevenLabsProvider(TTSProvider):
    id = "elevenlabs"

    def __init__(self):
        self.spec = ProviderSpec(
            id=self.id,
            name="ElevenLabs",
            kind="tts",
            default_model="eleven_multilingual_v2",
            models=["eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_flash_v2_5"],
            requires_key=True,
            key_hint="ElevenLabs API Key（xi-api-key）",
            docs="https://elevenlabs.io/docs/api-reference",
        )

    async def synthesize(
        self, *, text: str, voice: str, speed: str, emotion: str, out_path: Path, key: str = ""
    ) -> Usage:
        voice_id = voice or "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": self.spec.default_model,
            "voice_settings": {
                "stability": 0.45 if emotion in ("激昂", "欢快") else 0.6,
                "similarity_boost": 0.75,
                "style": 0.35,
                "use_speaker_boost": True,
            },
        }
        async with http_client(300.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 300:
            raise ProviderError(
                f"ElevenLabs 配音失败（{resp.status_code}）：{resp.text[:300]}", provider=self.id
            )
        out_path.write_bytes(resp.content)
        return Usage(self.id, self.spec.default_model, "tts", _duration_of(out_path), "seconds")

    async def test(self, key: str) -> dict:
        async with http_client(60.0) as client:
            resp = await client.get("https://api.elevenlabs.io/v1/user", headers={"xi-api-key": key})
        if resp.status_code >= 300:
            raise ProviderError(f"ElevenLabs 连接失败（{resp.status_code}）", provider=self.id)
        return {"ok": True, "message": "ElevenLabs 连接正常"}


# ---------------------------------------------------------------- 自定义


class CustomTTSProvider(TTSProvider):
    id = "custom-tts"

    def __init__(self):
        self.spec = ProviderSpec(
            id=self.id,
            name="自定义配音端点",
            kind="tts",
            default_model="custom",
            models=["custom"],
            requires_key=True,
            key_hint="填写完整的 HTTP 端点地址",
            note="POST JSON {text, voice, speed, emotion}，返回音频二进制",
        )

    async def synthesize(
        self, *, text: str, voice: str, speed: str, emotion: str, out_path: Path, key: str = ""
    ) -> Usage:
        endpoint = key
        if not endpoint.startswith("http"):
            raise ProviderError("自定义配音需要填写完整的 http(s) 端点", provider=self.id)
        payload = {
            "text": text,
            "voice": voice,
            "speed": round(self._speed_delta(speed), 2),
            "emotion": emotion,
        }
        async with http_client(300.0) as client:
            resp = await client.post(endpoint, json=payload)
        if resp.status_code >= 300:
            raise ProviderError(
                f"自定义配音失败（{resp.status_code}）：{resp.text[:300]}", provider=self.id
            )
        out_path.write_bytes(resp.content)
        return Usage(self.id, "custom", "tts", _duration_of(out_path), "seconds")

    async def test(self, key: str) -> dict:
        if not key.startswith("http"):
            return {"ok": False, "message": "端点地址需以 http:// 或 https:// 开头"}
        return {"ok": True, "message": "端点格式正确"}


# ---------------------------------------------------------------- 工具


def _duration_of(path: Path) -> float:
    """通过 ffprobe 读取音频时长；失败时返回 0。"""
    from media_core.config import BIN

    ffprobe = BIN.resolve("ffprobe")
    if not ffprobe or not path.exists():
        return 0.0
    try:
        import subprocess

        out = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return round(float(out.stdout.strip() or 0), 3)
    except Exception:  # noqa: BLE001
        return 0.0


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("'", "&apos;")
        .replace('"', "&quot;")
    )


def cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
