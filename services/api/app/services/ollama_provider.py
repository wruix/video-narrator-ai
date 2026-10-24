"""Ollama 原生协议适配器。

Ollama 的 /api/chat 接口与 OpenAI Chat Completions 不同：

请求：
  POST /api/chat
  {"model": "qwen2.5vl:3b", "messages": [{"role": "user", "content": "...", "images": ["base64..."]}], "stream": false, "options": {...}}

响应：
  {"message": {"role": "assistant", "content": "..."}, "done": true, ...}

用法：
  1. 本地启动 ollama serve，拉取模型：ollama pull qwen2.5vl:3b
  2. 在设置中填入任意密钥（Ollama 不要求 Key，填任意字符串即可）
  3. 选择分析模型 ollama，模型名填 qwen2.5vl:3b
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from ai_providers.base import (
    AnalysisRequest,
    ProviderError,
    ProviderSpec,
    ShotDraft,
    TextRequest,
    Usage,
    coerce_shots,
    encode_image,
    extract_json,
)

STYLE_HINTS = {
    "cinematic": "电影感，克制、有画面张力，像预告片旁白",
    "story": "故事叙述，代入感强，讲述人物与事件",
    "emotion": "情绪叙事，重氛围与心理描写",
    "product": "产品讲解，简洁专业，突出卖点",
    "knowledge": "知识科普，条理清晰，重解释",
    "documentary": "纪录片旁白，客观克制，有历史纵深",
}


class OllamaProvider:
    spec = ProviderSpec(
        id="ollama",
        name="Ollama（本地模型）",
        kind="vision",
        default_model="qwen2.5vl:3b",
        models=[
            "qwen2.5vl:3b",
            "qwen2.5vl:7b",
            "llama3.2-vision:11b",
            "llava:7b",
        ],
        requires_key=False,
        key_hint="Ollama 本地运行不需要 API Key，填任意字符串即可",
        docs="https://github.com/ollama/ollama/blob/main/docs/api.md",
        native_video=False,
        native_audio=False,
        note="本地运行，数据不出机器；模型需提前用 ollama pull 下载",
    )

    id = "ollama"

    async def analyze(self, req: AnalysisRequest) -> tuple[list[ShotDraft], Usage]:
        model = req.model or self.spec.default_model

        image_urls: list[str] = []
        for frame in req.frames[:6]:
            try:
                data_url = encode_image(frame.path)
                # Ollama 的 images 字段只需要纯 base64，不要 data:image/...;base64, 前缀
                b64 = data_url.split(",", 1)[-1] if "," in data_url else data_url
                image_urls.append(b64)
            except OSError:
                continue

        prompt_lines = _analysis_prompt(req)
        # 把关键帧的时间点标注在文本中，让模型能对应图像与时间
        content = prompt_lines + "\n" + "\n".join(
            f"[帧 {i}: {frame.timestamp:.1f}s]" for i, frame in enumerate(req.frames[:60])
        )

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一位专业的影视分镜师与视频解说撰稿人。只输出 JSON。",
                },
                {"role": "user", "content": content, "images": image_urls},
            ],
            "stream": False,
            "options": {"temperature": 0.35, "num_ctx": 16384},
        }

        base_url = (req.extra.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
        url = f"{base_url}/api/chat"
        async with httpx.AsyncClient(timeout=httpx.Timeout(req.extra.get("timeout", 900), connect=30)) as client:
            resp = await client.post(url, headers={"Content-Type": "application/json"}, json=payload)
        if resp.status_code >= 300:
            raise ProviderError(
                f"Ollama 调用失败（{resp.status_code}）：{resp.text[:500]}",
                provider=self.id,
                status=resp.status_code,
            )
        data = resp.json()
        message = data.get("message") or {}
        text = message.get("content") or ""
        if not text:
            raise ProviderError("Ollama 未返回文本内容", provider=self.id)

        shots = coerce_shots(extract_json(text), req.duration)
        if not shots:
            raise ProviderError("Ollama 未解析出任何镜头", provider=self.id)
        return shots, Usage(self.id, model, "vision", 0, "tokens")

    async def complete(self, req: TextRequest) -> tuple[str, Usage]:
        model = req.model or self.spec.default_model
        messages: list[dict[str, Any]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": req.temperature},
        }
        base_url = (req.extra.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
        url = f"{base_url}/api/chat"
        async with httpx.AsyncClient(timeout=httpx.Timeout(req.extra.get("timeout", 600), connect=30)) as client:
            resp = await client.post(url, headers={"Content-Type": "application/json"}, json=payload)
        if resp.status_code >= 300:
            raise ProviderError(
                f"Ollama 调用失败（{resp.status_code}）：{resp.text[:500]}",
                provider=self.id,
                status=resp.status_code,
            )
        data = resp.json()
        text = (data.get("message") or {}).get("content") or ""
        if not text:
            raise ProviderError("Ollama 未返回文本内容", provider=self.id)
        return text, Usage(self.id, model, "text", 0, "tokens")

    async def test(self, key: str) -> dict:
        payload: dict[str, Any] = {
            "model": self.spec.default_model,
            "messages": [{"role": "user", "content": "回复两个字：正常"}],
            "stream": False,
        }
        base_url = "http://127.0.0.1:11434"
        url = f"{base_url}/api/chat"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers={"Content-Type": "application/json"}, json=payload)
        if resp.status_code >= 300:
            raise ProviderError(
                f"Ollama 连接失败（{resp.status_code}）：{resp.text[:300]}",
                provider=self.id,
                status=resp.status_code,
            )
        text = (resp.json().get("message") or {}).get("content") or ""
        return {"ok": True, "message": text.strip()[:80]}


def _analysis_prompt(req: AnalysisRequest) -> str:
    lines = [
        "请分析这段视频的关键帧，并按镜头输出结构化 JSON。",
        "",
        "要求：",
        "1. 按画面内容切分镜头，给出每个镜头的 start / end（秒，保留 2 位小数）。",
        "2. visual：客观描述画面内容（人物、动作、场景、字幕）。",
        "3. narration：这一段的中文解说词，口语化、有画面感，不要复述字幕原文。",
        "4. dialogue：人物对白或旁白（听不清就留空）。",
        "5. emotion：情绪标签，取值范围 default / 平静 / 紧张 / 激昂 / 悲伤 / 欢快 / 悬疑 / 温情。",
        "6. 只输出 JSON，格式为 {\"shots\": [{\"start\":0.0,\"end\":5.2,\"visual\":\"\",\"narration\":\"\",\"dialogue\":\"\",\"emotion\":\"default\"}]}",
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
