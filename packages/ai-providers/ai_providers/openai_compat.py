"""OpenAI 兼容协议适配器。

同一套实现覆盖多个厂商，因为它们都遵循 `/chat/completions` 约定：
  * openai     — api.openai.com
  * doubao     — 火山方舟 ark.cn-beijing.volces.com/api/v3
  * siliconflow / compatible — 任意 OpenAI 兼容网关（Ollama、vLLM、本地推理等）

注意：OpenAI 标准接口只接受文本与图片，视频需先抽帧再送入。
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



class OpenAICompatProvider:
    """OpenAI 兼容的多模态 / 文本 provider。"""

    def __init__(
        self,
        *,
        provider_id: str,
        name: str,
        base_url: str,
        default_model: str,
        models: list[str],
        key_hint: str = "",
        docs: str = "",
        note: str = "",
        requires_key: bool = True,
    ):
        self.id = provider_id
        self.spec = ProviderSpec(
            id=provider_id,
            name=name,
            kind="vision",
            default_model=default_model,
            models=models,
            requires_key=requires_key,
            key_hint=key_hint,
            docs=docs,
            native_video=False,
            native_audio=False,
            note=note,
        )
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------ 内部

    def _endpoint(self, base_url: str | None) -> str:
        root = (base_url or self.base_url).rstrip("/")
        if root.endswith("/chat/completions"):
            return root
        if root.endswith("/v1"):
            return f"{root}/chat/completions"
        return f"{root}/chat/completions"

    async def _chat(
        self,
        *,
        key: str,
        model: str,
        messages: list[dict],
        temperature: float = 0.35,
        max_tokens: int = 8192,
        json_mode: bool = False,
        base_url: str | None = None,
        timeout: float = 600.0,
    ) -> tuple[str, Usage]:
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        url = self._endpoint(base_url)
        async with http_client(timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 300:
            raise ProviderError(
                f"{self.spec.name} 调用失败（{resp.status_code}）：{resp.text[:500]}",
                provider=self.id,
                status=resp.status_code,
            )
        data = safe_json(resp, self.id)
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"{self.spec.name} 未返回结果", provider=self.id)
        text = (choices[0].get("message") or {}).get("content") or ""
        if not text:
            raise ProviderError(f"{self.spec.name} 返回内容为空", provider=self.id)
        usage = data.get("usage") or {}
        units = float(usage.get("total_tokens") or usage.get("prompt_tokens") or 0)
        return text, Usage(self.id, model, "text", units, "tokens")

    # ------------------------------------------------------------ 接口

    async def analyze(self, req: AnalysisRequest) -> tuple[list[ShotDraft], Usage]:
        model = req.model or self.spec.default_model
        content: list[dict] = []
        for frame in req.frames[:60]:
            try:
                content.append({"type": "image_url", "image_url": {"url": encode_image(frame.path)}})
                content.append(
                    {"type": "text", "text": f"[该帧时间点 {frame.timestamp:.1f}s]"}
                )
            except OSError:
                continue
        content.append({"type": "text", "text": _analysis_prompt(req)})
        messages = [
            {
                "role": "system",
                "content": "你是一位专业的影视分镜师与视频解说撰稿人。你必须只输出 JSON。",
            },
            {"role": "user", "content": content},
        ]
        text, usage = await self._chat(
            key=req.key,
            model=model,
            messages=messages,
            temperature=0.35,
            max_tokens=8192,
            json_mode=True,
            base_url=req.extra.get("base_url"),
            timeout=req.extra.get("timeout", 600.0),
        )
        shots = coerce_shots(extract_json(text), req.duration)
        if not shots:
            raise ProviderError(f"{self.spec.name} 未解析出任何镜头", provider=self.id)
        usage.kind = "vision"
        return shots, usage

    async def complete(self, req: TextRequest) -> tuple[str, Usage]:
        model = req.model or self.spec.default_model
        messages: list[dict] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})
        return await self._chat(
            key=req.key,
            model=model,
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            json_mode=req.json_mode,
            base_url=req.extra.get("base_url"),
            timeout=req.extra.get("timeout", 600.0),
        )

    async def test(self, key: str, base_url: str | None = None) -> dict:
        text, usage = await self._chat(
            key=key,
            model=self.spec.default_model,
            messages=[{"role": "user", "content": "回复两个字：正常"}],
            max_tokens=32,
            base_url=base_url,
            timeout=60.0,
        )
        return {"ok": True, "message": text.strip()[:80], "usage": usage.units}


def _analysis_prompt(req: AnalysisRequest) -> str:
    return analysis_prompt(req).replace(
        "请分析这段视频，并按镜头输出结构化 JSON。",
        "请分析这段视频的关键帧，并按镜头输出结构化 JSON。",
    )
