"""成片合成：解说配音 + 原声压低 + 字幕 + 画面比例适配。

处理链路：
  1. 把每句配音转成统一规格的 WAV；
  2. 按镜头时间轴拼接成一条完整的解说轨（空隙补静音）；
  3. 单条 ffmpeg 命令完成：画面缩放/裁切 + 混音 + 烧字幕 + 编码输出。
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

from .config import SUBTITLE_FONT, SUBTITLE_FONT_SIZE
from .media import ffmpeg_bin, run
from .subtitle import SubtitleCue, render_srt

TARGETS = {
    "original": None,
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


@dataclass
class VoiceClip:
    """一条配音在时间轴上的位置。"""

    start: float
    path: Path
    text: str = ""


class ComposeError(RuntimeError):
    pass


# ---------------------------------------------------------------- 音频


async def _to_wav(src: Path, dst: Path) -> bool:
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "48000",
        "-c:a",
        "pcm_s16le",
        "-y",
        str(dst),
    ]
    code, _, err = await run(cmd, timeout=600)
    if code != 0:
        raise ComposeError(f"音频转换失败：{err[:300]}")
    return dst.exists()


async def build_narration_track(clips: list[VoiceClip], out_path: Path) -> tuple[float, float]:
    """拼接解说轨，返回 (总时长, 最后一段结束时刻)。"""
    if not clips:
        raise ComposeError("没有可用的配音片段")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wavs: list[Path] = []
    for idx, clip in enumerate(clips):
        wav = out_path.parent / f"seg_{idx:04d}.wav"
        await _to_wav(clip.path, wav)
        wavs.append(wav)

    cursor = 0.0
    end_time = 0.0
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(48000)
        for clip, wav in zip(clips, wavs):
            with wave.open(str(wav), "rb") as src:
                frames = src.readframes(src.getnframes())
                src_rate = src.getframerate()
                dur = src.getnframes() / float(src_rate or 48000)
            gap = clip.start - cursor
            if gap > 0.001:
                silence = b"\x00" * int(gap * 48000) * 2
                out.writeframes(silence)
                cursor += gap
            out.writeframes(frames)
            cursor += dur
            end_time = max(end_time, cursor)
            try:
                wav.unlink(missing_ok=True)
            except OSError:
                pass
    return round(end_time, 3), round(cursor, 3)


# ---------------------------------------------------------------- 视频


def _video_filter(aspect: str, subtitle_path: Path | None, burn: bool) -> str:
    filters: list[str] = []
    target = TARGETS.get(aspect)
    if target:
        w, h = target
        filters.append(
            f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        )
    else:
        filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")

    if burn and subtitle_path:
        escaped = _escape_filter_path(subtitle_path)
        style = (
            f"FontName={SUBTITLE_FONT},FontSize={SUBTITLE_FONT_SIZE},PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=48"
        )
        filters.append(f"subtitles='{escaped}':force_style='{style}'")
    return ",".join(filters)


def _escape_filter_path(path: Path) -> str:
    """Windows 路径在 ffmpeg 滤镜中需要转义冒号与反斜杠。"""
    s = str(path.resolve()).replace("\\", "/")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    s = s.replace("[", r"\[").replace("]", r"\]")
    return s


async def compose(
    *,
    source: Path,
    narration: Path,
    out_path: Path,
    aspect: str = "original",
    bgm_path: Path | None = None,
    bgm_volume: float = 0.12,
    original_volume: float = 0.15,
    subtitle_path: Path | None = None,
    burn_subtitles: bool = True,
    duration: float = 0.0,
    progress=None,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y"]
    cmd += ["-i", str(source)]
    cmd += ["-i", str(narration)]
    if bgm_path:
        cmd += ["-i", str(bgm_path)]

    filters: list[str] = []
    vf = _video_filter(aspect, subtitle_path, burn_subtitles)
    # 若解说超出视频长度，用最后一帧补足
    if duration > 0:
        vf = f"{vf},tpad=stop_mode=clone:stop_duration=0.001"
    filters.append(f"[0:v]{vf}[vout]")

    # 原声压低
    has_audio = _has_audio(source)
    if has_audio:
        filters.append(f"[0:a]volume={original_volume}[orig]")
    filters.append("[1:a]volume=1.0[voice]")

    if bgm_path:
        filters.append(f"[2:a]volume={bgm_volume},aloop=loop=-1:size=2e9[bgm]")

    mix_inputs = "[orig][voice]" if has_audio else "[voice]"
    mix_count = 2 if has_audio else 1
    if bgm_path:
        mix_inputs += "[bgm]"
        mix_count += 1
    filters.append(
        f"{mix_inputs}amix=inputs={mix_count}:duration=longest:normalize=0:dropout_transition=0[aout]"
    )

    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-movflags",
        "+faststart",
        str(out_path),
    ]

    code, _, err = await run(cmd, timeout=7200)
    if code != 0 or not out_path.exists():
        raise ComposeError(f"合成失败：{(err or '未知错误')[:600]}")
    return out_path


_AUDIO_CACHE: dict[str, bool] = {}


def _has_audio(path: Path) -> bool:
    key = str(path)
    if key in _AUDIO_CACHE:
        return _AUDIO_CACHE[key]
    from .media import ffprobe_bin, run_sync

    code, out, _ = run_sync(
        [
            ffprobe_bin(),
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ],
        timeout=60,
    )
    result = code == 0 and bool(out.strip())
    _AUDIO_CACHE[key] = result
    return result


def write_srt(cues: list[SubtitleCue], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_srt(cues), encoding="utf-8-sig")
    return path
