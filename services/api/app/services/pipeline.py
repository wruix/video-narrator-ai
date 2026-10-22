"""任务编排：把「上传 → 理解 → 文案 → 审核 → 配音 → 合成」串成一条流水线。

阶段划分：
    probe → shots → frames → asr → analyze → script → review(人工审核) → tts → subtitle → compose

其中 `review` 是阻塞点：自动检查通过后停下等待人工确认，确认后继续。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from ..config import DEFAULT_FRAME_INTERVAL, OUTPUT_DIR, SCENE_THRESHOLD, WORK_DIR
from ..db import Project, Render, Shot, UsageRecord
from ai_providers import (
    AnalysisRequest,
    ProviderError,
    ShotDraft,
    get_text,
    get_tts,
    get_vision,
)
from media_core import compose as compose_service
from media_core import frames as frames_service
from media_core import media as media_service
from media_core import subtitle as subtitle_service
from . import asr as asr_service
from .keyvault import resolve_key

ProgressFn = Callable[[float, str, str], None]

STAGE_LABELS = {
    "probe": "解析视频信息",
    "shots": "识别镜头切分",
    "frames": "抽取关键帧",
    "asr": "识别音频内容",
    "analyze": "模型理解视频",
    "script": "生成解说文案",
    "review": "等待人工审核",
    "tts": "合成配音",
    "subtitle": "生成字幕",
    "compose": "合成成片",
    "done": "完成",
}


class PipelineError(RuntimeError):
    pass


@dataclass
class RenderResult:
    render_id: int
    video_path: Path
    subtitle_path: Path | None


class Pipeline:
    def __init__(self, db: Session, project: Project, report: ProgressFn):
        self.db = db
        self.project = project
        self.report = report

    # ------------------------------------------------------------ 工具

    @property
    def project_dir(self) -> Path:
        return WORK_DIR / f"project_{self.project.id}"

    @property
    def frames_dir(self) -> Path:
        return self.project_dir / "frames"

    @property
    def audio_dir(self) -> Path:
        return self.project_dir / "audio"

    @property
    def tts_dir(self) -> Path:
        return self.project_dir / "tts"

    def source_video(self) -> Path:
        if not self.project.video_path:
            raise PipelineError("项目尚未上传视频")
        return Path(self.project.video_path)

    def _record_usage(self, usage, kind: str) -> None:
        self.db.add(
            UsageRecord(
                project_id=self.project.id,
                provider=usage.provider,
                model=usage.model,
                kind=kind,
                units=usage.units,
                unit_name=usage.unit_name,
                estimated_cost=usage.estimated_cost,
                note=usage.note,
            )
        )

    def _key(self, provider_id: str) -> str:
        key, _src = resolve_key(self.db, provider_id)
        return key or ""

    # ------------------------------------------------------------ 阶段 1-6

    async def analyze(self) -> None:
        p = self.project
        video = self.source_video()

        # --- 1. 探测 ---
        self.report(0.02, "probe", "解析视频信息")
        info = await media_service.probe(video)
        p.duration = info.duration
        p.width = info.width
        p.height = info.height
        p.fps = info.fps
        p.has_audio = info.has_audio
        self.db.commit()
        if info.duration <= 0:
            raise PipelineError("视频时长为 0，文件可能损坏")

        # --- 2. 镜头切分 ---
        self.report(0.06, "shots", "识别镜头切分")
        scenes = await media_service.detect_scene_changes(video, threshold=SCENE_THRESHOLD * 100)
        bounds = media_service.build_shot_boundaries(info.duration, scenes)
        if not bounds:
            bounds = [(0.0, info.duration)]
        shot_bounds = [
            frames_service.ShotBounds(index=i, start=a, end=b) for i, (a, b) in enumerate(bounds)
        ]

        # --- 3. 抽帧 ---
        self.report(0.12, "frames", "抽取关键帧")
        grouped = await frames_service.extract_shot_frames(
            video,
            shot_bounds,
            self.frames_dir,
            base_interval=DEFAULT_FRAME_INTERVAL,
            progress=lambda frac, msg: self.report(0.12 + frac * 0.18, "frames", msg),
        )
        total_frames = sum(len(v) for v in grouped.values())
        if total_frames == 0:
            raise PipelineError("未能从视频中抽取任何画面帧")

        # --- 4. 语音识别（可选） ---
        self.report(0.32, "asr", "识别音频内容")
        transcript_text = ""
        transcript_segments: list[dict] = []
        asr_provider = (p.asr_provider or "").strip()
        if info.has_audio and asr_provider and asr_provider != "none":
            try:
                asr_audio = self.audio_dir / "source.wav"
                await media_service.extract_audio(video, asr_audio)
                tr = await asr_service.transcribe(
                    asr_audio,
                    provider=asr_provider,
                    key=self._key(_asr_key_provider(asr_provider)),
                    language=p.language,
                )
                transcript_text = tr.text
                transcript_segments = tr.segments
            except Exception as exc:  # noqa: BLE001 - 识别失败不阻塞主流程
                self.report(0.36, "asr", f"语音识别跳过：{exc}")

        # --- 5. 模型理解视频 ---
        self.report(0.40, "analyze", "模型理解视频")
        provider = get_vision(p.analysis_model)
        key = self._key(p.analysis_model)
        if provider.spec.requires_key and not key:
            raise ProviderError(
                f"尚未配置 {provider.spec.name} 的 API Key，请先在「设置」中填写",
                provider=p.analysis_model,
            )
        frames_flat = [f for b in shot_bounds for f in grouped.get(b.index, [])]
        req = AnalysisRequest(
            video_path=video,
            frames=frames_flat,
            duration=info.duration,
            style=p.style,
            language=p.language,
            user_notes=p.user_notes or "",
            transcript=transcript_text,
            transcript_segments=transcript_segments,
            model="",
            key=key,
        )
        drafts, usage = await provider.analyze(req)
        self._record_usage(usage, "vision")
        self.db.commit()

        aligned = _align_shots(bounds, drafts)

        # --- 6. 文案优化（二次创作） ---
        self.report(0.70, "script", "生成解说文案")
        polished = await self._polish(aligned)
        if polished is not None:
            aligned = polished

        self._save_shots(aligned, grouped)
        self.report(0.85, "script", f"已生成 {len(aligned)} 个镜头的解说文案")
        self.report(0.90, "review", "等待人工审核")

    # ------------------------------------------------------------ 文案优化

    async def _polish(self, shots: list[dict]) -> list[dict] | None:
        p = self.project
        script_provider = p.script_model
        if not script_provider or script_provider == "none" or script_provider == p.analysis_model:
            return None
        key = self._key(script_provider)
        provider = get_text(script_provider)
        if provider.spec.requires_key and not key:
            return None

        payload = [
            {
                "index": i,
                "start": round(s["start"], 2),
                "end": round(s["end"], 2),
                "visual": s["visual"],
                "original_narration": s["narration"],
                "dialogue": s["dialogue"],
            }
            for i, s in enumerate(shots)
        ]
        prompt = (
            "你是一位视频解说撰稿人。请把下面每个镜头的初稿解说改写成更有画面感的成稿。\n"
            f"语言：{p.language}。风格要求：{p.style}。\n"
            "要求：\n"
            "1. 每条解说长度控制在 15-45 个字，适合朗读；\n"
            "2. 保留初稿的事实信息，但去掉重复的形容；\n"
            "3. 不要出现「这个视频」「画面中」这类多余前缀；\n"
            "4. 保持与原镜头一一对应，不要新增或删除条目。\n"
            "只输出 JSON：{\"narration\": [\"...\", \"...\"]}"
            f"\n\n镜头数据：\n{json.dumps(payload, ensure_ascii=False, indent=1)}"
        )
        from ai_providers.base import TextRequest

        try:
            text, usage = await provider.complete(
                TextRequest(
                    prompt=prompt,
                    system="你是专业的视频解说撰稿人。只输出 JSON。",
                    key=key,
                    temperature=0.75,
                    max_tokens=6000,
                    json_mode=True,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.report(0.75, "script", f"文案优化跳过：{exc}")
            return None

        self._record_usage(usage, "text")
        self.db.commit()
        try:
            from ai_providers.base import extract_json

            data = extract_json(text)
            narrations = data.get("narration") or data.get("list") or []
            if not isinstance(narrations, list) or len(narrations) != len(shots):
                return None
        except Exception:  # noqa: BLE001
            return None

        for shot, narration in zip(shots, narrations):
            if isinstance(narration, str) and narration.strip():
                shot["narration"] = narration.strip()
        return shots

    # ------------------------------------------------------------ 保存

    def _save_shots(self, shots: list[dict], grouped: dict[int, list]) -> None:
        p = self.project
        self.db.query(Shot).filter(Shot.project_id == p.id).delete()
        self.db.flush()
        for i, s in enumerate(shots):
            frames = [f.path.name for f in grouped.get(i, [])]
            self.db.add(
                Shot(
                    project_id=p.id,
                    index=i,
                    start=s["start"],
                    end=s["end"],
                    visual=s.get("visual", ""),
                    narration=s.get("narration", ""),
                    dialogue=s.get("dialogue", ""),
                    emotion=s.get("emotion", "default"),
                    frames=json.dumps(frames, ensure_ascii=False),
                )
            )
        self.db.commit()
        self.db.refresh(p)

    # ------------------------------------------------------------ 阶段 8-10

    async def render(self) -> RenderResult:
        p = self.project
        video = self.source_video()
        shots = sorted(
            self.db.query(Shot).filter(Shot.project_id == p.id).all(), key=lambda s: s.index
        )
        if not shots:
            raise PipelineError("尚无镜头文案，无法生成成片")

        # --- 8. 配音 ---
        self.report(0.05, "tts", "合成配音")
        tts = get_tts(p.tts_provider)
        tts_key = self._key(p.tts_provider)
        if tts.spec.requires_key and not tts_key:
            raise ProviderError(
                f"尚未配置 {tts.spec.name} 的凭证，请先在「设置」中填写", provider=p.tts_provider
            )
        self.tts_dir.mkdir(parents=True, exist_ok=True)

        clips: list[compose_service.VoiceClip] = []
        narration_entries: list[tuple[float, float, str]] = []
        cursor = 0.0
        for i, shot in enumerate(shots):
            text = (shot.narration or "").strip()
            if not text:
                continue
            out = self.tts_dir / f"shot_{shot.index:04d}.mp3"
            try:
                usage = await tts.synthesize(
                    text=text,
                    voice=p.voice_id,
                    speed=p.voice_speed,
                    emotion=shot.emotion or p.voice_emotion,
                    out_path=out,
                    key=tts_key,
                )
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise PipelineError(f"第 {i + 1} 句配音失败：{exc}") from exc
            self._record_usage(usage, "tts")
            self.db.commit()

            dur = usage.units or media_service.media_duration(out)
            shot.tts_audio = out.name
            shot.tts_duration = dur
            self.db.commit()

            start = max(cursor, shot.start)
            clips.append(compose_service.VoiceClip(start=start, path=out, text=text))
            narration_entries.append((start, start + dur, text))
            cursor = start + dur

        if not clips:
            raise PipelineError("所有镜头都没有解说词，请先撰写文案")

        self.report(0.55, "tts", f"完成 {len(clips)} 段配音")

        # --- 9. 字幕 ---
        self.report(0.62, "subtitle", "生成字幕")
        cues = subtitle_service.build_cues(narration_entries)
        subtitle_path: Path | None = None
        if p.subtitle_enabled and cues:
            subtitle_path = self.project_dir / f"subtitle_{p.id}.srt"
            compose_service.write_srt(cues, subtitle_path)

        # --- 10. 合成 ---
        self.report(0.68, "compose", "合成成片")
        narration_track = self.project_dir / "narration.wav"
        end_time, total = await compose_service.build_narration_track(clips, narration_track)

        out_dir = OUTPUT_DIR / f"project_{p.id}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"final_{int(asyncio.get_event_loop().time())}.mp4"

        await compose_service.compose(
            source=video,
            narration=narration_track,
            out_path=out_path,
            aspect=p.aspect or "original",
            bgm_volume=p.bgm_volume if p.bgm_volume else 0.0,
            original_volume=0.12,
            subtitle_path=subtitle_path,
            burn_subtitles=bool(p.burn_subtitles),
            duration=end_time,
        )

        final_duration = media_service.media_duration(out_path)
        render = Render(
            project_id=p.id,
            video_path=str(out_path),
            subtitle_path=str(subtitle_path) if subtitle_path else None,
            duration=final_duration or end_time,
            size=out_path.stat().st_size,
            width=0,
            height=0,
        )
        self.db.add(render)
        self.db.commit()
        self.db.refresh(render)
        self.report(0.99, "compose", "成片已生成")
        return RenderResult(render.id, out_path, subtitle_path)


# ---------------------------------------------------------------- 对齐


def _asr_key_provider(asr_provider: str) -> str:
    """语音识别服务与 API Key 的对应关系。"""
    return {
        "openai": "openai",
        "dashscope": "qwen",
        "local": "",
    }.get(asr_provider, "")


def _align_shots(bounds: list[tuple[float, float]], drafts: list[ShotDraft]) -> list[dict]:
    """把模型产出的镜头内容映射到本地检测出的镜头区间上。

    本地场景检测的时间轴更准确，模型的内容描述更可靠；
    以本地时间轴为准，按时间重叠度取模型对应片段的内容。
    """
    result: list[dict] = []
    for i, (start, end) in enumerate(bounds):
        best: ShotDraft | None = None
        best_overlap = 0.0
        for d in drafts:
            overlap = min(end, d.end) - max(start, d.start)
            if overlap > best_overlap:
                best_overlap = overlap
                best = d
        result.append(
            {
                "start": start,
                "end": end,
                "visual": best.visual if best else "",
                "narration": best.narration if best else "",
                "dialogue": best.dialogue if best else "",
                "emotion": (best.emotion if best else "default") or "default",
            }
        )
    return result
