"""通义千问（阿里云百炼 DashScope）适配器。

使用百炼的多模态生成接口 qwen-vl / qwen-omni：
  * 视觉：多模态生成接口，图片以 data URL 传入
  * 文本：兼容 OpenAI 的 /compatible-mode/v1/chat/completions

参考：https://help.aliyun.com/zh/model-studio/
"""

from __future__ import annotations



from .base import (
    http_client,
    AnalysisRequest,
    analysis_prompt,
    ProviderError,
    ProviderSpec,
    ShotDraft,
    TextRequest,
    Usage,
    coerce_shots,
    encode_image,
    extract_json,
    safe_json,
)

MULTIMODAL_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
COMPAT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"



class QwenProvider:
    spec = ProviderSpec(
        id="qwen",
        name="通义千问 / Qwen Omni",
        kind="vision",
        default_model="qwen-vl-max",
        models=[
            "qwen-vl-max",
            "qwen-vl-plus",
            "qwen-omni-turbo",
            "qwen2.5-vl-72b-instruct",
            "qwen3-vl-plus",
        ],
        key_hint="阿里云百炼控制台创建 API Key（DASHSCOPE_API_KEY）",
        docs="https://help.aliyun.com/zh/model-studio/vision",
        native_video=False,
        native_audio=True,
        note="中文视频理解与对白理解表现好，可作为 Gemini 的备选",
    )

    id = "qwen"

    async def analyze(self, req: AnalysisRequest) -> tuple[list[ShotDraft], Usage]:
        model = req.model or self.spec.default_model
        content: list[dict] = []
        for frame in req.frames[:60]:
            try:
                content.append({"image": encode_image(frame.path)})
            except OSError:
                continue
        content.append({"text": _analysis_prompt(req)})
        payload = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {
                "result_format": "message",
                "temperature": 0.35,
                "max_tokens": 8192,
            },
        }
        headers = {
            "Authorization": f"Bearer {req.key}",
            "Content-Type": "application/json",
        }
        async with http_client(req.extra.get("timeout", 900)) as client:
            resp = await client.post(MULTIMODAL_URL, headers=headers, json=payload)
        if resp.status_code >= 300:
            raise ProviderError(
                f"千问调用失败（{resp.status_code}）：{resp.text[:500]}",
                provider=self.id,
                status=resp.status_code,
            )
        data = safe_json(resp, self.id)
        usage_meta = data.get("usage") or {}
        text = _extract_content(data)
        if not text:
            raise ProviderError("千问未返回文本内容", provider=self.id)
        units = float(usage_meta.get("total_tokens") or 0)
        shots = coerce_shots(extract_json(text), req.duration)
        if not shots:
            raise ProviderError("千问未解析出任何镜头", provider=self.id)
        return shots, Usage(self.id, model, "vision", units, "tokens")

    async def complete(self, req: TextRequest) -> tuple[str, Usage]:
        model = req.model or self.spec.default_model
        messages: list[dict] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        }
        if req.json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {req.key}",
            "Content-Type": "application/json",
        }
        async with http_client(req.extra.get("timeout", 600)) as client:
            resp = await client.post(f"{COMPAT_BASE}/chat/completions", headers=headers, json=payload)
        if resp.status_code >= 300:
            raise ProviderError(
                f"千问调用失败（{resp.status_code}）：{resp.text[:500]}",
                provider=self.id,
                status=resp.status_code,
            )
        data = safe_json(resp, self.id)
        choices = data.get("choices") or []
        text = (choices[0].get("message") or {}).get("content") or ""
        if not text:
            raise ProviderError("千问返回内容为空", provider=self.id)
        usage_meta = data.get("usage") or {}
        units = float(usage_meta.get("total_tokens") or 0)
        return text, Usage(self.id, model, "text", units, "tokens")

    async def test(self, key: str) -> dict:
        payload = {
            "model": self.spec.default_model,
            "messages": [{"role": "user", "content": "回复两个字：正常"}],
            "max_tokens": 32,
        }
        headers = {"Authorization": f"Bearer {key}"}
        async with http_client(60.0) as client:
            resp = await client.post(f"{COMPAT_BASE}/chat/completions", headers=headers, json=payload)
        if resp.status_code >= 300:
            raise ProviderError(
                f"千问连接失败（{resp.status_code}）：{resp.text[:300]}",
                provider=self.id,
                status=resp.status_code,
            )
        data = resp.json()
        text = (data["choices"][0]["message"]["content"] or "").strip()
        return {"ok": True, "message": text[:80]}


def _extract_content(data: dict) -> str:
    output = data.get("output") or {}
    choices = output.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            parts = [c.get("text", "") for c in content if isinstance(c, dict)]
            return "\n".join(p for p in parts if p)
        if isinstance(content, str):
            return content
    # 兼容旧版 result 字段
    result = data.get("result")
    if isinstance(result, str):
        return result
    return ""


def _analysis_prompt(req: AnalysisRequest) -> str:
    return analysis_prompt(req).replace(
        "请分析这段视频，并按镜头输出结构化 JSON。",
        "请分析这段视频的关键帧，并按镜头输出结构化 JSON。",
    )
