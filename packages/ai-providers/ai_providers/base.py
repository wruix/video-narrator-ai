"""多模型适配层的基础类型与公共工具。

所有厂商的差异都被收敛到两类接口：
  * VisionProvider —— 理解视频，产出逐镜头草稿
  * TextProvider   —— 对文案做二次创作（润色 / 改写 / 结构优化）

上层 pipeline 只依赖这些接口，因此新增一个厂商只需要实现接口 + 注册。
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

import httpx

# FrameSample 定义在 media-core（媒体概念），此处再导出以便调用方统一从 base 导入
from media_core.types import FrameSample  # noqa: F401

ProviderKind = Literal["vision", "text", "tts"]


# ---------------------------------------------------------------- 元数据



@dataclass
class ProviderSpec:
    id: str
    name: str
    kind: ProviderKind
    default_model: str
    models: list[str] = field(default_factory=list)
    requires_key: bool = True
    key_hint: str = ""
    docs: str = ""
    # 能力标记
    native_video: bool = False   # 可直接上传视频文件
    native_audio: bool = False   # 可直接读取音轨
    vision: bool = True          # 支持图片输入
    max_image_bytes: int = 4 * 1024 * 1024
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "default_model": self.default_model,
            "models": self.models,
            "requires_key": self.requires_key,
            "key_hint": self.key_hint,
            "docs": self.docs,
            "native_video": self.native_video,
            "native_audio": self.native_audio,
            "vision": self.vision,
            "note": self.note,
        }


# ---------------------------------------------------------------- 数据载体



@dataclass
class ShotDraft:
    """模型产出的单个镜头草稿。"""

    start: float
    end: float
    visual: str = ""
    narration: str = ""
    dialogue: str = ""
    emotion: str = "default"

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "visual": self.visual,
            "narration": self.narration,
            "dialogue": self.dialogue,
            "emotion": self.emotion,
        }


@dataclass
class AnalysisRequest:
    video_path: Path | None
    frames: list[FrameSample]
    duration: float
    style: str
    language: str = "zh-CN"
    user_notes: str = ""
    transcript: str = ""
    transcript_segments: list[dict] = field(default_factory=list)
    model: str = ""
    key: str = ""
    extra: dict = field(default_factory=dict)
    video_url: str = ""  # 供需要公网地址的厂商使用


@dataclass
class TextRequest:
    prompt: str
    system: str = ""
    model: str = ""
    key: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    json_mode: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class Usage:
    provider: str
    model: str
    kind: str
    units: float = 0.0
    unit_name: str = "tokens"
    estimated_cost: float = 0.0
    note: str = ""


class ProviderError(RuntimeError):
    """厂商调用失败，消息面向最终用户展示。"""

    def __init__(self, message: str, *, provider: str = "", status: int | None = None):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status = status


# ---------------------------------------------------------------- 公共工具


def encode_image(path: Path, max_bytes: int = 4 * 1024 * 1024) -> str:
    """读取图片并返回 data URL。超过上限时会被调用方降采样处理。"""
    data = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def safe_json(resp: httpx.Response, provider: str = "") -> Any:
    """解析响应体；厂商偶尔会返回 HTML/纯文本，这里转成可读错误。"""
    try:
        return resp.json()
    except ValueError:
        text = (resp.text or "")[:300].strip()
        raise ProviderError(
            f"模型服务返回了非 JSON 内容（HTTP {resp.status_code}）：{text or '空响应'}",
            provider=provider,
            status=resp.status_code,
        )


def extract_json(text: str) -> Any:
    """从模型输出中稳健地抽取 JSON（容忍 markdown 围栏、前后缀说明文字）。"""
    if not text:
        raise ProviderError("模型返回了空内容")
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 退回扫描第一个平衡的 { } 或 [ ]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ProviderError("模型返回的内容不是合法 JSON")


def coerce_shots(raw: Any, duration: float) -> list[ShotDraft]:
    """把模型返回的多种结构统一成 ShotDraft 列表。"""
    items: list[Any] = []
    if isinstance(raw, dict):
        for key in ("shots", "segments", "scenes", "list", "data"):
            if isinstance(raw.get(key), list):
                items = raw[key]
                break
        else:
            items = [raw]
    elif isinstance(raw, list):
        items = raw

    shots: list[ShotDraft] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        start = _as_float(
            item.get("start", item.get("start_time", item.get("begin", item.get("t0")))), idx
        )
        end = _as_float(
            item.get("end", item.get("end_time", item.get("finish", item.get("t1")))), None
        )
        if end is None or end <= start:
            end = start + 1.0
        if duration > 0:
            start = max(0.0, min(start, duration))
            end = max(start + 0.2, min(end, duration))
        visual = _first_str(item, ("visual", "description", "画面", "scene", "content"))
        narration = _first_str(
            item, ("narration", "narration_text", "commentary", "解说", "解说词", "text")
        )
        dialogue = _first_str(item, ("dialogue", "speech", "对白", "audio"))
        emotion = _first_str(item, ("emotion", "tone", "mood")) or "default"
        shots.append(
            ShotDraft(
                start=start,
                end=end,
                visual=visual,
                narration=narration,
                dialogue=dialogue,
                emotion=emotion,
            )
        )
    shots.sort(key=lambda s: s.start)
    return shots


def _as_float(value: Any, fallback: Any) -> float:
    if value is None:
        return float(fallback) if fallback is not None else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # 支持 "0:12" / "00:01:02" / "12.5"
        m = re.match(r"^(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)$", value.strip())
        if m:
            parts = [p for p in m.groups() if p is not None]
            total = 0.0
            for p in parts:
                total = total * 60 + float(p)
            return total
        try:
            return float(value)
        except ValueError:
            pass
    return float(fallback) if fallback is not None else 0.0


def _first_str(item: dict, keys: Iterable[str]) -> str:
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
    return ""


STYLE_HINTS = {
    "cinematic": "电影感，克制、有画面张力，像预告片旁白",
    "story": "故事叙述，代入感强，讲述人物与事件",
    "emotion": "情绪叙事，重氛围与心理描写",
    "product": "产品讲解，简洁专业，突出卖点",
    "knowledge": "知识科普，条理清晰，重解释",
    "documentary": "纪录片旁白，客观克制，有历史纵深",
}

EMOTION_VALUES = "default / 平静 / 紧张 / 激昂 / 悲伤 / 欢快 / 悬疑 / 温情"

SHOT_SCHEMA = (
    '{"shots": [{"start":0.0,"end":5.2,"visual":"","narration":"",'
    '"dialogue":"","emotion":"default"}]}'
)


def analysis_prompt(req: "AnalysisRequest") -> str:
    """构造各厂商共用的镜头分析提示词。"""
    lines = [
        "请分析这段视频，并按镜头输出结构化 JSON。",
        "",
        "要求：",
        "1. 按画面内容切分镜头，给出每个镜头的 start / end（秒，保留 2 位小数）。",
        "2. visual：客观描述画面内容（人物、动作、场景、字幕）。",
        "3. narration：这一段的中文解说词，口语化、有画面感，不要复述字幕原文。",
        "4. dialogue：人物对白或旁白（听不清就留空）。",
        f"5. emotion：情绪标签，取值范围 {EMOTION_VALUES}。",
        f"6. 只输出 JSON，格式为 {SHOT_SCHEMA}",
        "",
        f"视频总时长约 {req.duration:.1f} 秒。",
        f"解说风格：{STYLE_HINTS.get(req.style, req.style)}",
        f"语言：{req.language}",
    ]
    if req.transcript:
        lines.append("")
        lines.append("以下是自动识别的音频文本（可能不完整，仅供理解内容，不要直接朗读）：")
        lines.append(req.transcript[:6000])
    if req.user_notes:
        lines.append("")
        lines.append(f"用户补充要求：{req.user_notes}")
    return "\n".join(lines)


def chunked(items: list, size: int) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ---------------------------------------------------------------- HTTP


@asynccontextmanager
async def http_client(
    timeout: float = 600.0,
    connect: float = 30.0,
    **kwargs,
):
    """统一的 HTTP 客户端：把底层网络异常翻译成用户能看懂的提示。

    httpx 默认 trust_env=True，会自动读取 HTTP_PROXY / HTTPS_PROXY 环境变量，
    因此在需要代理的机器上无需改代码。
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=connect), **kwargs) as client:
            yield client
    except httpx.ConnectTimeout as exc:
        raise ProviderError(
            "连接模型服务超时。请检查网络连通性，或设置 HTTP_PROXY / HTTPS_PROXY 代理后重试。"
        ) from exc
    except httpx.ReadTimeout as exc:
        raise ProviderError("读取模型响应超时，服务可能繁忙，或上传的视频过大。") from exc
    except httpx.ConnectError as exc:
        raise ProviderError(
            f"无法连接到模型服务：{exc}。请检查网络连通性，或设置 HTTP_PROXY / HTTPS_PROXY 代理。"
        ) from exc
    except httpx.ProxyError as exc:
        raise ProviderError(f"代理连接失败：{exc}。请检查 HTTP_PROXY / HTTPS_PROXY 配置。") from exc
    except httpx.HTTPError as exc:
        raise ProviderError(f"网络请求失败：{exc}") from exc
