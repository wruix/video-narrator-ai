"""Gemini 适配器：原生视频理解（Files API）+ 关键帧回退。

参考官方文档：
  * 文件上传（可续传）：https://ai.google.dev/gemini-api/docs/files
  * 视频理解：https://ai.google.dev/gemini-api/docs/video-understanding
  * 免费层单文件上限 2GB；付费层更高，受配额约束。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx

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
    extract_json,
    safe_json,
)

BASE = "https://generativelanguage.googleapis.com"
UPLOAD_BASE = "https://generativelanguage.googleapis.com/upload/v1beta"


class GeminiProvider:
    spec = ProviderSpec(
        id="gemini",
        name="Google Gemini",
        kind="vision",
        default_model="gemini-2.5-flash",
        models=[
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
        ],
        key_hint="在 Google AI Studio 申请 API Key（免费层即可）",
        docs="https://ai.google.dev/gemini-api/docs/video-understanding",
        native_video=True,
        native_audio=True,
        note="唯一支持原生上传整段视频的模型，推荐用于镜头分析",
    )

    id = "gemini"

    # ------------------------------------------------------------ 文件上传

    async def _upload_file(self, client: httpx.AsyncClient, path: Path, key: str) -> str:
        """通过可续传上传接口把本地文件送到 Gemini，返回 file uri。"""
        size = path.stat().st_size
        mime = _guess_mime(path)
        headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime,
            "x-goog-api-key": key,
        }
        start_url = f"{UPLOAD_BASE}/files"
        async with client.stream("POST", start_url, headers=headers, timeout=None) as resp:
            if resp.status_code >= 300:
                body = await resp.aread()
                raise ProviderError(
                    f"Gemini 文件上传初始化失败：{body.decode('utf-8', 'ignore')[:400]}",
                    provider=self.id,
                    status=resp.status_code,
                )
            upload_url = resp.headers.get("x-goog-upload-url")
        if not upload_url:
            raise ProviderError("Gemini 未返回上传地址", provider=self.id)

        payload = path.read_bytes()
        put_headers = {
            "Content-Length": str(size),
            "Content-Type": mime,
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
            "x-goog-api-key": key,
        }
        async with client.put(upload_url, content=payload, headers=put_headers) as resp:
            if resp.status_code >= 300:
                body = await resp.aread()
                raise ProviderError(
                    f"Gemini 文件上传失败：{body.decode('utf-8', 'ignore')[:400]}",
                    provider=self.id,
                    status=resp.status_code,
                )
            data = resp.json()

        file_obj = data.get("file") or data
        file_uri = file_obj.get("uri") or ""
        name = file_obj.get("name") or ""
        if not file_uri:
            raise ProviderError("Gemini 上传成功但未返回文件 URI", provider=self.id)

        # 等待文件处理完成（视频需要转码）
        await self._wait_ready(client, name, key)
        return file_uri, name

    async def _wait_ready(self, client: httpx.AsyncClient, name: str, key: str) -> None:
        if not name:
            return
        deadline = time.time() + 1800
        while time.time() < deadline:
            resp = await client.get(f"{BASE}/v1beta/{name}", headers={"x-goog-api-key": key})
            if resp.status_code >= 300:
                return
            state = (resp.json().get("state") or "").upper()
            if state in ("ACTIVE", "STATE_UNSPECIFIED"):
                return
            if state == "FAILED":
                raise ProviderError("Gemini 处理视频文件失败", provider=self.id)
            await asyncio.sleep(3)

    async def _delete_file(self, client: httpx.AsyncClient, name: str, key: str) -> None:
        if not name:
            return
        try:
            await client.delete(f"{BASE}/v1beta/{name}", headers={"x-goog-api-key": key})
        except Exception:  # noqa: BLE001 - 清理失败不影响主流程
            pass

    # ------------------------------------------------------------ 生成

    async def _generate(
        self, client: httpx.AsyncClient, model: str, key: str, payload: dict
    ) -> tuple[str, Usage]:
        url = f"{BASE}/v1beta/models/{model}:generateContent"
        resp = await client.post(url, headers={"x-goog-api-key": key}, json=payload)
        if resp.status_code >= 300:
            raise ProviderError(
                f"Gemini 调用失败（{resp.status_code}）：{resp.text[:500]}",
                provider=self.id,
                status=resp.status_code,
            )
        data = safe_json(resp, self.id)
        candidates = data.get("candidates") or []
        text_parts = []
        for cand in candidates:
            for part in (cand.get("content") or {}).get("parts", []):
                if isinstance(part, dict) and part.get("text"):
                    text_parts.append(part["text"])
        if not text_parts:
            raise ProviderError("Gemini 未返回文本内容", provider=self.id)
        usage_meta = data.get("usageMetadata") or {}
        units = float(usage_meta.get("totalTokenCount") or 0)
        return "\n".join(text_parts), Usage(self.id, model, "vision", units, "tokens")

    async def analyze(self, req: AnalysisRequest) -> tuple[list[ShotDraft], Usage]:
        model = req.model or self.spec.default_model
        parts: list[dict] = []
        async with http_client(req.extra.get("timeout", 900)) as client:
            file_uri = ""
            file_name = ""
            use_native = bool(req.extra.get("use_native_video", True)) and req.video_path
            if use_native:
                try:
                    file_uri, file_name = await self._upload_file(
                        client, Path(req.video_path), req.key
                    )
                    parts.append(
                        {
                            "file_data": {
                                "file_uri": file_uri,
                                "mime_type": _guess_mime(Path(req.video_path)),
                            }
                        }
                    )
                except ProviderError:
                    # 原生上传失败时回退到抽帧分析
                    file_uri = ""
            try:
                if not file_uri:
                    parts.extend(_frame_parts(req))
                parts.append({"text": analysis_prompt(req)})
                payload = {
                    "contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {
                        "temperature": 0.35,
                        "maxOutputTokens": 8192,
                        "responseMimeType": "application/json",
                    },
                    "systemInstruction": {
                        "parts": [
                            {
                                "text": "你是一位专业的影视分镜师与视频解说撰稿人。只输出 JSON。"
                            }
                        ]
                    },
                }
                text, usage = await self._generate(client, model, req.key, payload)
            finally:
                if file_name:
                    await self._delete_file(client, file_name, req.key)

        shots = coerce_shots(extract_json(text), req.duration)
        if not shots:
            raise ProviderError("Gemini 未解析出任何镜头", provider=self.id)
        return shots, usage

    async def complete(self, req: TextRequest) -> tuple[str, Usage]:
        model = req.model or self.spec.default_model
        payload: dict = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": req.prompt}],
                }
            ],
            "generationConfig": {"temperature": req.temperature, "maxOutputTokens": req.max_tokens},
        }
        if req.system:
            payload["systemInstruction"] = {"parts": [{"text": req.system}]}
        async with http_client(req.extra.get("timeout", 600)) as client:
            text, usage = await self._generate(client, model, req.key, payload)
        usage.kind = "text"
        return text, usage

    async def test(self, key: str) -> dict:
        model = self.spec.default_model
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "回复两个字：正常"}]}],
            "generationConfig": {"maxOutputTokens": 32},
        }
        async with http_client(60.0) as client:
            text, usage = await self._generate(client, model, key, payload)
        return {"ok": True, "message": text.strip()[:80], "usage": usage.units}


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".m4v": "video/x-m4v",
        ".avi": "video/x-msvideo",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def _frame_parts(req: AnalysisRequest) -> list[dict]:
    parts: list[dict] = []
    for frame in req.frames[:60]:
        try:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": _b64(frame.path)}})
        except OSError:
            continue
    return parts


def _b64(path: Path) -> str:
    import base64

    return base64.b64encode(path.read_bytes()).decode("ascii")


