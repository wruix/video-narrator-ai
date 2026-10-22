"""语音识别（ASR）：可选能力，用于让模型理解原片对白。

支持三种后端：
  * openai    — Whisper API（/audio/transcriptions）
  * dashscope — 阿里云百炼 Paraformer（中文识别较好）
  * local     — 本地 faster-whisper（需额外安装）

识别失败不会中断整体流程，pipeline 会退化为「仅画面分析」。
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from pathlib import Path

from ai_providers.base import ProviderError, http_client, safe_json


@dataclass
class Transcript:
    text: str = ""
    segments: list[dict] = field(default_factory=list)
    provider: str = ""
    language: str = "zh"

    def to_dict(self) -> dict:
        return {"text": self.text, "segments": self.segments, "provider": self.provider}


async def transcribe(
    audio_path: Path,
    *,
    provider: str,
    key: str,
    language: str = "zh",
    model: str = "",
) -> Transcript:
    if provider in ("", "none"):
        return Transcript(provider="none")
    if provider == "openai":
        return await _openai_whisper(audio_path, key=key, language=language, model=model)
    if provider == "dashscope":
        return await _dashscope_paraformer(audio_path, key=key)
    if provider == "local":
        return await _local_whisper(audio_path, language=language)
    raise ProviderError(f"未知的语音识别服务：{provider}", provider=provider)


async def _openai_whisper(
    audio_path: Path, *, key: str, language: str, model: str
) -> Transcript:
    url = "https://api.openai.com/v1/audio/transcriptions"
    lang = {"zh": "zh", "zh-CN": "zh"}.get(language, "zh")
    data = {
        "model": model or "whisper-1",
        "language": lang,
        "response_format": "verbose_json",
    }
    async with http_client(900) as client:
        with audio_path.open("rb") as fh:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                data=data,
                files={"file": (audio_path.name, fh, "audio/wav")},
            )
    if resp.status_code >= 300:
        raise ProviderError(
            f"Whisper 识别失败（{resp.status_code}）：{resp.text[:300]}", provider="openai"
        )
    payload = resp.json()
    segments = [
        {
            "start": float(s.get("start", 0)),
            "end": float(s.get("end", 0)),
            "text": (s.get("text") or "").strip(),
        }
        for s in payload.get("segments") or []
    ]
    text = (payload.get("text") or "").strip()
    if not text:
        text = " ".join(s["text"] for s in segments if s["text"])
    return Transcript(text=text, segments=segments, provider="openai", language=lang)


async def _dashscope_paraformer(audio_path: Path, *, key: str) -> Transcript:
    """百炼录音文件识别：Files API 上传 → 提交异步任务 → 轮询 → 拉取结果。"""
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    files_url = "https://dashscope.aliyuncs.com/api/v1/files"
    task_url = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
    tasks_base = "https://dashscope.aliyuncs.com/api/v1/tasks"

    async with http_client(900) as client:
        content = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        resp = await client.post(
            files_url,
            headers=headers,
            json={"purpose": "recognition", "file_name": audio_path.name, "content": content},
        )
        if resp.status_code >= 300:
            raise ProviderError(
                f"百炼文件上传失败（{resp.status_code}）：{resp.text[:300]}", provider="dashscope"
            )
        file_id = (safe_json(resp, "dashscope").get("output") or {}).get("file_id")
        if not file_id:
            raise ProviderError("百炼未返回 file_id", provider="dashscope")

        resp = await client.post(
            task_url,
            headers=headers,
            json={
                "model": "paraformer-v2",
                "input": {"file_ids": [file_id]},
                "parameters": {"channel_id": [0], "language_hints": ["zh"]},
            },
        )
        if resp.status_code >= 300:
            raise ProviderError(
                f"百炼识别任务提交失败（{resp.status_code}）：{resp.text[:300]}", provider="dashscope"
            )
        task_id = (safe_json(resp, "dashscope").get("output") or {}).get("task_id")
        if not task_id:
            raise ProviderError("百炼未返回 task_id", provider="dashscope")

        deadline = 900
        elapsed = 0
        output: dict = {}
        while elapsed < deadline:
            await asyncio.sleep(3)
            elapsed += 3
            resp = await client.get(f"{tasks_base}/{task_id}", headers=headers)
            if resp.status_code >= 300:
                raise ProviderError(f"百炼任务查询失败（{resp.status_code}）", provider="dashscope")
            data = safe_json(resp, "dashscope")
            output = data.get("output") or {}
            status = str(output.get("task_status") or "").upper()
            if status == "SUCCEEDED":
                break
            if status in ("FAILED", "CANCELED", "UNKNOWN"):
                raise ProviderError(
                    f"百炼识别任务失败：{output.get('message') or status}", provider="dashscope"
                )
        else:
            raise ProviderError("百炼识别任务超时", provider="dashscope")

    segments: list[dict] = []
    text = ""
    for result in output.get("results") or []:
        url = result.get("transcription_url")
        if not url:
            continue
        async with http_client(120) as client:
            r = await client.get(url)
        if r.status_code >= 300:
            continue
        payload = safe_json(r, "dashscope")
        for item in payload.get("transcription", []) or []:
            seg_text = (item.get("text") or "").strip()
            if not seg_text:
                continue
            text += seg_text
            segments.append(
                {
                    "start": round(float(item.get("begin_time", 0)) / 1000, 3),
                    "end": round(float(item.get("end_time", 0)) / 1000, 3),
                    "text": seg_text,
                }
            )
    return Transcript(text=text.strip(), segments=segments, provider="dashscope", language="zh")


async def _local_whisper(audio_path: Path, *, language: str) -> Transcript:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise ProviderError(
            "未安装本地识别模型，请执行 pip install faster-whisper", provider="local"
        ) from exc

    model = WhisperModel("small", device="auto", compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path), language="zh" if language.startswith("zh") else None
    )
    out_segments = []
    parts = []
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        parts.append(text)
        out_segments.append(
            {"start": round(float(seg.start), 3), "end": round(float(seg.end), 3), "text": text}
        )
    return Transcript(
        text=" ".join(parts),
        segments=out_segments,
        provider="local",
        language=getattr(info, "language", "zh") or "zh",
    )
