"""端到端自检：不依赖任何大模型 API Key，验证 FFmpeg 媒体链路是否完整。

流程：
  1. 用 FFmpeg 合成一段带场景切换的测试视频
  2. 场景检测 → 镜头边界
  3. 抽帧
  4. Edge TTS 合成解说（免费）
  5. 生成 SRT 字幕
  6. 混音 + 烧字幕 + 输出 MP4
  7. 校验产物

用法： .\\backend\\.venv\\Scripts\\python.exe scripts\\selftest.py
"""

from __future__ import annotations

import asyncio
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.config import ensure_dirs  # noqa: E402
from ai_providers import get_tts  # noqa: E402
from ai_providers.base import ProviderError  # noqa: E402
from media_core import compose as compose_service  # noqa: E402
from media_core import frames as frames_service  # noqa: E402
from media_core import media as media_service  # noqa: E402
from media_core import subtitle as subtitle_service  # noqa: E402

WORK = ROOT / "data" / "selftest"


def ok(msg: str) -> None:
    print(f"  \033[92m✓\033[0m {msg}")


def fail(msg: str) -> None:
    print(f"  \033[91m✗\033[0m {msg}")


def step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


async def make_test_video(path: Path) -> None:
    """合成一段 12 秒、3 个场景的测试视频。"""
    cmd = [
        media_service.ffmpeg_bin(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1280x720:rate=25:duration=4",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x1f4e79:size=1280x720:rate=25:duration=4",
        "-f",
        "lavfi",
        "-i",
        "smptebars=size=1280x720:rate=25:duration=4",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=330:duration=12:sample_rate=44100",
        "-filter_complex",
        "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    code, _, err = await media_service.run(cmd, timeout=600)
    if code != 0:
        raise RuntimeError(f"生成测试视频失败：{err[:400]}")


async def main() -> int:
    ensure_dirs()
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)

    total = 7
    video = WORK / "test.mp4"

    step(1, total, "合成测试视频")
    await make_test_video(video)
    ok(f"{video.name}  {video.stat().st_size / 1024:.0f} KB")

    step(2, total, "探测视频信息")
    info = await media_service.probe(video)
    ok(f"{info.width}x{info.height} · {info.duration:.1f}s · {info.fps:.2f}fps · 音轨={info.has_audio}")
    if info.duration < 1:
        fail("时长异常")
        return 1

    step(3, total, "场景检测与镜头切分")
    scenes = await media_service.detect_scene_changes(video, threshold=10.0)
    bounds = media_service.build_shot_boundaries(info.duration, scenes)
    ok(f"检测到 {len(scenes)} 个场景变化 → {len(bounds)} 个镜头")
    for a, b in bounds[:8]:
        print(f"      {a:6.2f}s → {b:6.2f}s")

    step(4, total, "抽取关键帧")
    shot_bounds = [
        frames_service.ShotBounds(index=i, start=a, end=b) for i, (a, b) in enumerate(bounds)
    ]
    grouped = await frames_service.extract_shot_frames(video, shot_bounds, WORK / "frames")
    n_frames = sum(len(v) for v in grouped.values())
    ok(f"共抽取 {n_frames} 帧")
    if n_frames == 0:
        fail("未抽到任何帧")
        return 1

    step(5, total, "Edge TTS 合成配音")
    tts = get_tts("edge")
    clips = []
    entries = []
    cursor = 0.0
    scripts = [
        "画面亮起，故事从这里正式开始。",
        "色调骤然转冷，暗示着某种变故正在发生。",
        "彩条闪过，像一段被抹去的记忆。",
    ]
    tts_dir = WORK / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    for i, (a, b) in enumerate(bounds):
        text = scripts[i % len(scripts)]
        out = tts_dir / f"shot_{i}.mp3"
        try:
            usage = await tts.synthesize(
                text=text, voice="zh-CN-XiaoxiaoNeural", speed="+0%", emotion="default",
                out_path=out, key="",
            )
        except ProviderError as exc:
            fail(f"配音失败：{exc.message}")
            return 1
        dur = usage.units or media_service.media_duration(out)
        start = max(cursor, a)
        clips.append(compose_service.VoiceClip(start=start, path=out, text=text))
        entries.append((start, start + dur, text))
        cursor = start + dur
    ok(f"生成 {len(clips)} 段配音，总时长 {cursor:.1f}s")

    step(6, total, "生成字幕并合成成片")
    cues = subtitle_service.build_cues(entries)
    srt = WORK / "subtitle.srt"
    compose_service.write_srt(cues, srt)
    ok(f"SRT {len(cues)} 条 -> {srt.name}")

    narration = WORK / "narration.wav"
    end_time, total_len = await compose_service.build_narration_track(clips, narration)
    ok(f"解说轨 {total_len:.1f}s")

    out_mp4 = WORK / "final.mp4"
    await compose_service.compose(
        source=video,
        narration=narration,
        out_path=out_mp4,
        aspect="16:9",
        bgm_volume=0.0,
        original_volume=0.15,
        subtitle_path=srt,
        burn_subtitles=True,
        duration=end_time,
    )
    size_mb = out_mp4.stat().st_size / 1048576
    dur = media_service.media_duration(out_mp4)
    ok(f"成片 {out_mp4.name} · {dur:.1f}s · {size_mb:.2f} MB")

    step(7, total, "校验产物")
    problems = []
    if dur < 1:
        problems.append("成片时长异常")
    if size_mb < 0.05:
        problems.append("成片体积异常")
    if not srt.exists() or srt.stat().st_size == 0:
        problems.append("字幕文件为空")
    if not any(WORK.glob("frames/*.jpg")):
        problems.append("未生成关键帧")

    if problems:
        for p in problems:
            fail(p)
        return 1
    ok("全部校验通过")
    print(f"\n  产物目录： {WORK}")
    print("  可以用播放器打开 final.mp4 查看效果。\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
