"""生成一个演示项目，用于快速查看界面各步骤的效果。

用法： .\\backend\\.venv\\Scripts\\python.exe scripts\\seed_demo.py [base_url]
"""

from __future__ import annotations

import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
VIDEO = ROOT / "data" / "selftest" / "test.mp4"


def req(path: str, method: str = "GET", body=None, raw=None, ctype=None):
    data = raw
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if ctype:
        headers["Content-Type"] = ctype
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=300) as resp:
        payload = resp.read()
        try:
            return json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return payload


SAMPLES = [
    (0.0, 3.5, "彩色测试图案，网格缓慢流动，画面干净", "天还没亮，城市先醒了。", "平静"),
    (3.5, 7.0, "整屏沉静的蓝，光线一点点铺开", "第一班公交驶过路口，灯光在柏油路上拖出一条长长的尾巴。", "温情"),
    (7.0, 10.5, "标准彩条依次闪过，颜色干脆利落", "有人推开便利店的门，风铃响了一声，新的一天正式开始。", "欢快"),
    (10.5, 12.0, "画面定格，光线逐渐稳定", "而这座城市，还从不知道自己被这样注视过。", "激昂"),
]


def main() -> int:
    if not VIDEO.exists():
        print("缺少测试视频，请先运行 scripts\\selftest.py")
        return 1

    proj = req("/api/projects", "POST", {"name": "演示项目 · 城市清晨"})
    pid = proj["id"]

    boundary = "----seedboundary"
    parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="file"; filename="demo.mp4"\r\n',
        b"Content-Type: video/mp4\r\n\r\n",
        VIDEO.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    req(
        f"/api/projects/{pid}/video",
        "POST",
        raw=b"".join(parts),
        ctype=f"multipart/form-data; boundary={boundary}",
    )
    req(
        f"/api/projects/{pid}",
        "PATCH",
        {
            "style": "cinematic",
            "aspect": "16:9",
            "analysis_model": "gemini",
            "script_model": "openai",
            "tts_provider": "edge",
            "voice_id": "zh-CN-YunxiNeural",
            "user_notes": "视频是城市清晨的纪录短片，请突出光影与街道的细节。",
        },
    )

    from app.db import Project, SessionLocal, Shot  # noqa: E402

    db = SessionLocal()
    try:
        db.query(Shot).filter(Shot.project_id == pid).delete()
        for i, (a, b, visual, narration, emotion) in enumerate(SAMPLES):
            db.add(
                Shot(
                    project_id=pid,
                    index=i,
                    start=a,
                    end=b,
                    visual=visual,
                    narration=narration,
                    emotion=emotion,
                    frames="[]",
                )
            )
        project = db.get(Project, pid)
        project.duration = 12.0
        project.width = 1280
        project.height = 720
        project.fps = 25.0
        project.has_audio = True
        project.status = "awaiting_review"
        db.commit()
    finally:
        db.close()

    print(f"演示项目已创建： id={pid}")
    print(f"  地址： {BASE}/")
    print("  在左侧项目列表中选择「演示项目 · 城市清晨」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
