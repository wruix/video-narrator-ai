"""字幕生成：依据解说时间轴输出 SRT。

解说时间轴的构造规则：
  * 每个镜头的配音从该镜头的 start 时刻开始；
  * 若上一段配音尚未结束，则顺延，避免两段人声重叠；
  * 字幕按句子长度切分，单行不超过 18 个汉字，最多两行。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str


def format_timestamp(seconds: float, sep: str = ",") -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace(".", sep)


def split_sentences(text: str) -> list[str]:
    """按中文标点切句，并按最大长度二次切分。"""
    if not text:
        return []
    raw = re.split(r"(?<=[。！？!?；;\n])\s*", text.strip())
    out: list[str] = []
    for part in raw:
        part = part.strip()
        if not part:
            continue
        if len(part) <= 24:
            out.append(part)
            continue
        # 超长句按逗号继续切
        chunks = re.split(r"(?<=[，,、])\s*", part)
        buf = ""
        for c in chunks:
            if not buf:
                buf = c
            elif len(buf) + len(c) <= 24:
                buf += c
            else:
                out.append(buf)
                buf = c
        if buf:
            out.append(buf)
    return out


def build_cues(
    entries: list[tuple[float, float, str]],
    *,
    max_chars: int = 18,
    min_duration: float = 0.8,
) -> list[SubtitleCue]:
    """entries: [(开始秒, 结束秒, 文本)]"""
    cues: list[SubtitleCue] = []
    for start, end, text in entries:
        if not text.strip():
            continue
        sentences = split_sentences(text)
        if not sentences:
            continue
        total = sum(len(s) for s in sentences) or 1
        cursor = start
        span = max(end - start, min_duration)
        for s in sentences:
            # 按字数比例分配时长
            ratio = len(s) / total
            dur = max(min_duration, span * ratio)
            # 单条字幕最多两行，每行 max_chars
            if len(s) > max_chars * 2:
                s = s[: max_chars * 2]
            cues.append(SubtitleCue(start=cursor, end=cursor + dur, text=s))
            cursor += dur
    # 去掉重叠
    for i in range(1, len(cues)):
        if cues[i].start < cues[i - 1].end:
            cues[i].start = cues[i - 1].end
        if cues[i].end <= cues[i].start:
            cues[i].end = cues[i].start + 0.4
    return cues


def render_srt(cues: list[SubtitleCue]) -> str:
    lines: list[str] = []
    for i, cue in enumerate(cues, start=1):
        lines.append(str(i))
        lines.append(f"{format_timestamp(cue.start)} --> {format_timestamp(cue.end)}")
        lines.append(cue.text)
        lines.append("")
    return "\n".join(lines)


def wrap_cjk(text: str, max_chars: int = 18) -> str:
    """中文按字数折行，英文按空格折行。"""
    if len(text) <= max_chars:
        return text
    if re.search(r"[\u4e00-\u9fff]", text):
        mid = len(text) // 2
        return f"{text[:mid]}\n{text[mid:]}"
    words = text.split()
    half = len(words) // 2 or 1
    return " ".join(words[:half]) + "\n" + " ".join(words[half:])
