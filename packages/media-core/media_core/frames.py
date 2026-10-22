"""关键帧抽取策略。

思路：
  1. 先按镜头边界得到基础镜头列表；
  2. 每个镜头按固定间隔抽若干帧作为基础帧；
  3. 计算相邻帧的像素差异，识别出「快速运动」区间；
  4. 在这些区间追加中间帧，避免只看固定间隔而漏掉关键动作。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from .config import MAX_FRAMES_PER_SHOT, MAX_FRAMES_TOTAL
from .types import FrameSample
from .media import extract_frame

try:  # Pillow 用于帧间差异计算，缺失时降级为等间隔抽帧
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover
    Image = None  # type: ignore


@dataclass
class ShotBounds:
    index: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def plan_timestamps(
    bounds: list[ShotBounds],
    *,
    base_interval: float = 2.0,
    motion_threshold: float = 18.0,
) -> list[float]:
    """规划全片抽帧时间点。"""
    plan: list[float] = []
    for b in bounds:
        dur = b.duration
        if dur <= 0:
            continue
        count = max(1, min(MAX_FRAMES_PER_SHOT, int(dur // base_interval) + 1))
        step = dur / count
        for i in range(count):
            # 稍微避开精确边界，取镜头内部
            ts = b.start + step * i + min(0.15, step * 0.2)
            plan.append(round(min(ts, b.end - 0.05), 3))
    return sorted(set(plan))


async def extract_shot_frames(
    video: Path,
    bounds: list[ShotBounds],
    out_dir: Path,
    *,
    base_interval: float = 2.0,
    motion_threshold: float = 18.0,
    progress=None,
) -> dict[int, list[FrameSample]]:
    """抽取所有镜头的关键帧，返回 {镜头索引: [FrameSample]}。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = plan_timestamps(bounds, base_interval=base_interval)
    if len(plan) > MAX_FRAMES_TOTAL:
        step = len(plan) / MAX_FRAMES_TOTAL
        plan = [plan[int(i * step)] for i in range(MAX_FRAMES_TOTAL)]

    frames: list[FrameSample] = []
    for i, ts in enumerate(plan):
        path = out_dir / f"f_{i:04d}.jpg"
        if await extract_frame(video, ts, path):
            frames.append(FrameSample(timestamp=ts, path=path))
        if progress and i % 5 == 0:
            progress(i / max(1, len(plan)) * 0.9, f"抽取关键帧 {i + 1}/{len(plan)}")

    extras = await _dense_for_motion(video, frames, bounds, out_dir, motion_threshold=motion_threshold)

    grouped: dict[int, list[FrameSample]] = {b.index: [] for b in bounds}
    for sample in frames + extras:
        for b in bounds:
            if b.start <= sample.timestamp < b.end or (
                b is bounds[-1] and sample.timestamp >= b.start
            ):
                grouped[b.index].append(sample)
                break
    for key in grouped:
        grouped[key].sort(key=lambda s: s.timestamp)
    return grouped


async def _dense_for_motion(
    video: Path,
    frames: list[FrameSample],
    bounds: list[ShotBounds],
    out_dir: Path,
    *,
    motion_threshold: float,
) -> list[FrameSample]:
    """检测快速运动片段并补抽中间帧。"""
    if Image is None or len(frames) < 3:
        return []

    loop = asyncio.get_running_loop()
    diffs = await loop.run_in_executor(None, _compute_diffs, frames)

    # 找出差异峰值所在的时间点
    peaks: list[float] = []
    for i in range(1, len(diffs)):
        if diffs[i] >= motion_threshold:
            peaks.append(frames[i].timestamp)
    if not peaks:
        return []

    extra_ts: list[float] = []
    for ts in peaks:
        prev_ts = frames[0].timestamp
        for f in frames:
            if f.timestamp < ts:
                prev_ts = f.timestamp
            else:
                break
        mid = (prev_ts + ts) / 2
        if 0 <= mid <= (bounds[-1].end if bounds else 0):
            extra_ts.append(round(mid, 3))

    extra_ts = sorted(set(extra_ts))[:40]
    extras: list[FrameSample] = []
    for i, ts in enumerate(extra_ts):
        path = out_dir / f"x_{i:04d}.jpg"
        if await extract_frame(video, ts, path):
            extras.append(FrameSample(timestamp=ts, path=path))
    return extras


def _compute_diffs(frames: list[FrameSample]) -> list[float]:
    """相邻帧的平均绝对差（0-255 尺度）。"""
    diffs: list[float] = [0.0]
    prev = None
    for f in frames:
        try:
            with Image.open(f.path) as im:
                small = im.convert("L").resize((64, 64))
                data = list(small.getdata())
        except Exception:  # noqa: BLE001
            diffs.append(0.0)
            continue
        if prev is not None:
            total = sum(abs(a - b) for a, b in zip(data, prev))
            diffs.append(total / len(data))
        else:
            diffs.append(0.0)
        prev = data
    return diffs
