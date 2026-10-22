# @vns/media-core

Vendor-agnostic video processing: FFmpeg wrapper, shot detection, keyframe extraction,
subtitle generation and final composition.

This package knows **nothing** about any model vendor or about the web framework.
That is what keeps the dependency graph one-way.

## Install

```bash
pip install -e packages/media-core
```

## What it provides

| Module | Purpose |
| --- | --- |
| `media_core.config` | FFmpeg/FFprobe discovery, frame-extraction and subtitle constants |
| `media_core.media` | `probe()`, scene detection, shot boundary building, frame extraction, audio extraction, WAV concatenation |
| `media_core.frames` | Keyframe planning and adaptive extraction (fast-motion detection) |
| `media_core.subtitle` | Sentence splitting, cue building, SRT rendering |
| `media_core.compose` | Narration track assembly, aspect-ratio handling, audio mixing, subtitle burn-in, MP4 output |
| `media_core.types` | `FrameSample` |

## Example

```python
from pathlib import Path
from media_core import media, frames, compose, subtitle

info = await media.probe(Path("input.mp4"))
scenes = await media.detect_scene_changes(Path("input.mp4"), threshold=10)
bounds = media.build_shot_boundaries(info.duration, scenes)

shot_bounds = [frames.ShotBounds(index=i, start=a, end=b) for i, (a, b) in enumerate(bounds)]
grouped = await frames.extract_shot_frames(Path("input.mp4"), shot_bounds, Path("out/frames"))

cues = subtitle.build_cues([(0.0, 3.2, "第一句解说")])
subtitle_path = compose.write_srt(cues, Path("out/subtitle.srt"))

await compose.compose(
    source=Path("input.mp4"),
    narration=Path("out/narration.wav"),
    out_path=Path("out/final.mp4"),
    aspect="16:9",
    subtitle_path=subtitle_path,
    burn_subtitles=True,
)
```

## Licence

Apache-2.0, same as the parent repository.
