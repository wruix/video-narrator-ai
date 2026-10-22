"""FFmpeg / FFprobe 封装：探测、镜头切分、抽帧、音轨提取。

所有外部进程调用都集中在这里，方便统一超时、日志与错误提示。
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import BIN
from .types import FrameSample


class MediaError(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    exe = BIN.resolve("ffmpeg")
    if not exe:
        raise MediaError(
            "未找到 ffmpeg。请安装 FFmpeg 并加入 PATH，或设置环境变量 VC_FFMPEG 指向可执行文件。"
        )
    return exe


def ffprobe_bin() -> str:
    exe = BIN.resolve("ffprobe")
    if not exe:
        raise MediaError(
            "未找到 ffprobe。请安装 FFmpeg 并加入 PATH，或设置环境变量 VC_FFPROBE 指向可执行文件。"
        )
    return exe


async def run(cmd: list[str], timeout: float = 3600.0) -> tuple[int, str, str]:
    """执行命令并返回 (returncode, stdout, stderr)。"""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise MediaError(f"命令执行超时：{cmd[0]}")
    return proc.returncode or 0, out.decode("utf-8", "ignore"), err.decode("utf-8", "ignore")


def run_sync(cmd: list[str], timeout: float = 3600.0) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return proc.returncode, proc.stdout.decode("utf-8", "ignore"), proc.stderr.decode("utf-8", "ignore")


# ---------------------------------------------------------------- 探测


@dataclass
class MediaInfo:
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    video_codec: str = ""
    audio_codec: str = ""
    bitrate: int = 0
    rotation: int = 0


def _parse_fps(rate: str) -> float:
    if not rate or rate in ("0/0",):
        return 0.0
    try:
        num, _, den = rate.partition("/")
        d = float(den or 1)
        return round(float(num) / d, 3) if d else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


async def probe(path: Path) -> MediaInfo:
    code, out, err = await run(
        [
            ffprobe_bin(),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout=300,
    )
    if code != 0:
        raise MediaError(f"无法读取视频信息：{err[:300] or out[:300]}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise MediaError("解析 ffprobe 输出失败") from exc

    info = MediaInfo()
    fmt = data.get("format") or {}
    try:
        info.duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        info.duration = 0.0
    try:
        info.bitrate = int(fmt.get("bit_rate") or 0)
    except (TypeError, ValueError):
        info.bitrate = 0

    for stream in data.get("streams") or []:
        kind = stream.get("codec_type")
        if kind == "video" and not info.width:
            info.width = int(stream.get("width") or 0)
            info.height = int(stream.get("height") or 0)
            info.video_codec = stream.get("codec_name") or ""
            info.fps = _parse_fps(stream.get("avg_frame_rate") or "")
            if not info.fps:
                info.fps = _parse_fps(stream.get("r_frame_rate") or "")
            for sd in stream.get("side_data_list") or []:
                if "rotation" in sd:
                    try:
                        info.rotation = int(sd["rotation"])
                    except (TypeError, ValueError):
                        pass
        elif kind == "audio" and not info.has_audio:
            info.has_audio = True
            info.audio_codec = stream.get("codec_name") or ""
    return info


# ---------------------------------------------------------------- 镜头切分


_SCDET_RE = re.compile(r"lavfi\.scd\.time:\s*([0-9.]+)")
_SCDET_SCORE_RE = re.compile(r"lavfi\.scd\.score:\s*([0-9.]+)")
_PTS_TIME_RE = re.compile(r"pts_time:([0-9.]+)")


async def detect_scene_changes(path: Path, threshold: float = 10.0) -> list[tuple[float, float]]:
    """返回 [(时间秒, 场景分)]，分数越高表示画面变化越剧烈。"""
    # 优先使用 scdet 滤镜（ffmpeg >= 4.4）
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-vf",
        f"scdet=threshold={threshold}",
        "-an",
        "-f",
        "null",
        "-",
    ]
    code, _, err = await run(cmd, timeout=1800)
    scenes: list[tuple[float, float]] = []
    if code == 0:
        for line in err.splitlines():
            m_time = _SCDET_RE.search(line)
            m_score = _SCDET_SCORE_RE.search(line)
            if m_time and m_score:
                scenes.append((float(m_time.group(1)), float(m_score.group(1))))
    if scenes:
        return scenes

    # 回退：select + showinfo
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-vf",
        "select='gt(scene,0.15)',showinfo",
        "-an",
        "-f",
        "null",
        "-",
    ]
    code, _, err = await run(cmd, timeout=1800)
    for line in err.splitlines():
        m = _PTS_TIME_RE.search(line)
        if m:
            scenes.append((float(m.group(1)), 20.0))
    return scenes


def build_shot_boundaries(
    duration: float,
    scenes: list[tuple[float, float]],
    *,
    min_shot_len: float = 1.2,
    max_shot_len: float = 12.0,
    max_shots: int = 120,
) -> list[tuple[float, float]]:
    """把场景变化点整理成 [(start, end)] 镜头区间。"""
    if duration <= 0:
        return [(0.0, 5.0)]

    cuts = sorted({round(t, 3) for t, _ in scenes if 0.2 < t < duration - 0.2})

    bounds: list[float] = [0.0]
    for c in cuts:
        if c - bounds[-1] >= min_shot_len:
            bounds.append(c)
    if duration - bounds[-1] > 0.05:
        bounds.append(duration)

    # 拆分过长的镜头，保证后续抽帧密度合理
    refined: list[float] = [0.0]
    for i in range(len(bounds) - 1):
        seg_start, seg_end = bounds[i], bounds[i + 1]
        span = seg_end - seg_start
        if span > max_shot_len:
            parts = int(span // max_shot_len) + 1
            step = span / parts
            for k in range(1, parts):
                refined.append(round(seg_start + step * k, 3))
        refined.append(seg_end)

    shots = list(zip(refined[:-1], refined[1:]))
    # 合并过短尾巴
    if len(shots) > 1 and (shots[-1][1] - shots[-1][0]) < min_shot_len:
        last = shots.pop()
        shots[-1] = (shots[-1][0], last[1])

    if len(shots) > max_shots:
        # 均匀抽稀
        step = len(shots) / max_shots
        picked = [shots[int(i * step)] for i in range(max_shots)]
        shots = picked

    return [(round(a, 3), round(b, 3)) for a, b in shots if b - a > 0.2]


# ---------------------------------------------------------------- 抽帧


async def extract_frame(video: Path, timestamp: float, out_path: Path, quality: int = 3) -> bool:
    """在指定时间点抽取一帧，返回是否成功。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        str(quality),
        "-y",
        str(out_path),
    ]
    code, _, err = await run(cmd, timeout=300)
    if code != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        return False
    return True


async def extract_frames(
    video: Path, timestamps: list[float], out_dir: Path, prefix: str = "f"
) -> list[FrameSample]:
    """批量抽帧，返回成功的结果。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    samples: list[FrameSample] = []
    for idx, ts in enumerate(timestamps):
        name = f"{prefix}_{idx:04d}.jpg"
        ok = await extract_frame(video, ts, out_dir / name)
        if ok:
            samples.append(FrameSample(timestamp=round(ts, 3), path=out_dir / name))
    return samples


async def extract_audio(video: Path, out_path: Path) -> bool:
    """提取音轨为 16k 单声道 WAV（供 ASR 使用）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-y",
        str(out_path),
    ]
    code, _, _ = await run(cmd, timeout=1800)
    return code == 0 and out_path.exists() and out_path.stat().st_size > 0


# ---------------------------------------------------------------- 拼接


async def concat_audio(parts: list[Path], out_path: Path) -> bool:
    """把多段音频按顺序拼接（使用 concat demuxer + 重编码）。"""
    if not parts:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_path.parent / f"{out_path.stem}_concat.txt"
    lines = []
    for p in parts:
        escaped = str(p.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-y",
        str(out_path),
    ]
    code, _, err = await run(cmd, timeout=1800)
    try:
        list_file.unlink(missing_ok=True)
    except OSError:
        pass
    if code != 0:
        raise MediaError(f"拼接配音失败：{err[:300]}")
    return out_path.exists()


def media_duration(path: Path) -> float:
    try:
        out = run_sync(
            [
                ffprobe_bin(),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            timeout=120,
        )[1]
        return round(float(out.strip() or 0), 3)
    except Exception:  # noqa: BLE001
        return 0.0
