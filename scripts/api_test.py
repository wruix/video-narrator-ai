"""API 级集成测试：走真实 HTTP 接口，覆盖上传 → 镜头写入 → 配音 → 成片 → 下载。

注意：这里直接往数据库写入镜头数据，用来在没有大模型 API Key 的环境下
验证「分析之后的全部链路」（配音、字幕、合成、导出）。

用法： .\\backend\\.venv\\Scripts\\python.exe scripts\\api_test.py [base_url]
"""

from __future__ import annotations

import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
VIDEO = ROOT / "data" / "selftest" / "test.mp4"

GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def req(path: str, method: str = "GET", body=None, raw: bytes | None = None, ctype=None):
    url = f"{BASE}{path}"
    print(f"      >> {method} {url}", flush=True)
    data = raw
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if ctype:
        headers["Content-Type"] = ctype
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            payload = resp.read()
            try:
                return resp.status, json.loads(payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return resp.status, payload
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"{method} {path} -> {e.code}: {detail[:400]}") from e


def main() -> int:
    total = 7
    if not VIDEO.exists():
        print(f"缺少测试视频：{VIDEO}\n请先运行 scripts\\selftest.py")
        return 1

    step(1, total, "健康检查")
    status, health = req("/api/health")
    if status != 200 or health.get("status") != "ok":
        fail(f"服务异常：{health}")
        return 1
    ok(f"服务就绪 · FFmpeg={health.get('ffmpeg')}")

    step(2, total, "创建项目")
    _, proj = req("/api/projects", "POST", {"name": "集成测试"})
    pid = proj["id"]
    ok(f"项目 #{pid} 已创建")

    step(3, total, "上传视频")
    boundary = "----opencodeboundary"
    video_bytes = VIDEO.read_bytes()
    parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="file"; filename="test.mp4"\r\n',
        b"Content-Type: video/mp4\r\n\r\n",
        video_bytes,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    status, res = req(
        f"/api/projects/{pid}/video",
        "POST",
        raw=b"".join(parts),
        ctype=f"multipart/form-data; boundary={boundary}",
    )
    ok(f"上传完成 · {res['size'] / 1024:.0f} KB")

    step(4, total, "写入镜头数据（模拟模型分析结果）")
    from app.db import SessionLocal, Shot  # noqa: E402

    db = SessionLocal()
    try:
        db.query(Shot).filter(Shot.project_id == pid).delete()
        samples = [
            (0.0, 4.0, "彩色测试图，网格状图案缓慢流动", "画面亮起，故事从这里正式开始。"),
            (4.0, 8.0, "整屏深蓝色，色调骤然转冷", "色调骤然转冷，暗示着某种变故正在发生。"),
            (8.0, 12.0, "标准测试彩条，色彩依次排列", "彩条闪过，像一段被抹去的记忆。"),
        ]
        for i, (a, b, visual, narration) in enumerate(samples):
            db.add(
                Shot(
                    project_id=pid,
                    index=i,
                    start=a,
                    end=b,
                    visual=visual,
                    narration=narration,
                    emotion="default",
                    frames="[]",
                )
            )
        db.commit()
    finally:
        db.close()
    ok(f"写入 {len(samples)} 个镜头")

    step(5, total, "审核通过")
    _, appr = req(f"/api/projects/{pid}/approve", "POST")
    ok(f"审核通过 · 镜头 {appr['shots']} 个 · 空文案 {appr['empty']} 个")

    step(6, total, "触发成片生成")
    _, job = req(f"/api/projects/{pid}/render", "POST")
    ok(f"任务已启动 · job #{job['id']}")
    last = ""
    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(2)
        _, detail = req(f"/api/projects/{pid}")
        active = [j for j in detail.get("jobs", []) if j["status"] == "running"]
        if active:
            j = active[0]
            msg = f"{j['detail']} {int(j['progress'] * 100)}% {j['message']}"
            if msg != last:
                print(f"      {CYAN}{msg}{RESET}")
                last = msg
            continue
        done = detail.get("jobs", [])[0]
        if done["status"] == "failed":
            fail(f"任务失败：{done.get('error') or done.get('message')}")
            return 1
        break
    else:
        fail("任务超时")
        return 1
    ok("成片生成完成")

    step(7, total, "校验成片与下载")
    _, detail = req(f"/api/projects/{pid}")
    renders = detail.get("renders", [])
    if not renders:
        fail("没有成片记录")
        return 1
    r = renders[0]
    ok(f"成片 #{r['id']} · {r['duration']:.1f}s · {r['size'] / 1048576:.2f} MB · 字幕={r['has_subtitle']}")

    status, blob = req(f"/api/projects/{pid}/renders/{r['id']}/download")
    if status != 200 or not isinstance(blob, (bytes, bytearray)) or len(blob) < 100000:
        fail(f"下载异常：status={status} size={len(blob) if isinstance(blob,(bytes,bytearray)) else 'n/a'}")
        return 1
    ok(f"下载成功 · {len(blob) / 1048576:.2f} MB")

    if r["has_subtitle"]:
        status, srt = req(f"/api/projects/{pid}/renders/{r['id']}/subtitle")
        text = srt.decode("utf-8-sig", "ignore") if isinstance(srt, (bytes, bytearray)) else ""
        ok(f"字幕下载成功 · {len(text.splitlines())} 行")
        print(f"      首条：{text.splitlines()[2] if len(text.splitlines()) > 2 else ''}")

    # 清理测试项目
    req(f"/api/projects/{pid}", "DELETE")
    ok("测试项目已清理")

    print("\n  全部通过 ✓\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
