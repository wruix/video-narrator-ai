"""Provider 适配层的离线测试：用打桩响应验证请求构造与结果解析。

不联网，因此可以在没有 API Key 的环境下检查：
  * 请求体是否符合各厂商协议
  * 返回的 JSON 能否正确解析成 ShotDraft
  * 镜头对齐逻辑是否正确
  * 异常返回是否被转换成可读错误

用法： .\\backend\\.venv\\Scripts\\python.exe scripts\\test_providers.py
"""

from __future__ import annotations

import asyncio
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

import httpx  # noqa: E402

from ai_providers import get_text, get_vision  # noqa: E402
from ai_providers.base import AnalysisRequest, FrameSample, ProviderError, TextRequest  # noqa: E402

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

failures: list[str] = []


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def bad(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")
    failures.append(msg)


class FakeTransport(httpx.AsyncBaseTransport):
    """记录请求并返回预设响应。"""

    def __init__(self, responder):
        self.responder = responder
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responder(request)


_ORIG_INIT = httpx.AsyncClient.__init__


def install(responder):
    transport = FakeTransport(responder)

    def patched(self, *args, **kwargs):
        kwargs["transport"] = transport
        _ORIG_INIT(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = patched  # type: ignore[method-assign]
    return transport


def restore():
    httpx.AsyncClient.__init__ = _ORIG_INIT  # type: ignore[method-assign]


SHOT_JSON = {
    "shots": [
        {
            "start": 0.0,
            "end": 4.2,
            "visual": "街道全景，行人走过",
            "narration": "清晨的街道开始苏醒。",
            "dialogue": "",
            "emotion": "平静",
        },
        {
            "start": 4.2,
            "end": 9.8,
            "visual": "特写：一只手推开玻璃门",
            "narration": "有人推开了那扇门。",
            "dialogue": "早啊。",
            "emotion": "温情",
        },
    ]
}


async def test_gemini() -> None:
    print("\n[Gemini · 原生视频 + 关键帧]")
    captured: dict = {}

    def responder(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode("utf-8", "ignore")
        captured["headers"] = dict(request.headers)
        if "upload" in str(request.url) and request.method == "POST":
            return httpx.Response(
                200, headers={"x-goog-upload-url": "https://upload.example/session"}, content=b""
            )
        if "upload.example" in str(request.url):
            return httpx.Response(
                200, json={"file": {"uri": "https://files.example/abc", "name": "files/abc"}}
            )
        if "/v1beta/files/abc" in str(request.url):
            return httpx.Response(200, json={"state": "ACTIVE"})
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": json.dumps(SHOT_JSON, ensure_ascii=False)}]}}],
                "usageMetadata": {"totalTokenCount": 1234},
            },
        )

    transport = install(responder)
    try:
        provider = get_vision("gemini")
        frames_dir = ROOT / "data" / "selftest" / "frames"
        frames = [FrameSample(t, p) for t, p in [(1.0, frames_dir / "f_0000.jpg"), (5.0, frames_dir / "f_0001.jpg")] if p.exists()]
        req = AnalysisRequest(
            video_path=None,
            frames=frames,
            duration=12.0,
            style="cinematic",
            key="fake-key",
            model="gemini-2.5-flash",
        )
        shots, usage = await provider.analyze(req)
        if len(shots) != 2:
            bad(f"应解析出 2 个镜头，实际 {len(shots)}")
        else:
            ok(f"解析出 {len(shots)} 个镜头")
        if shots[0].narration != "清晨的街道开始苏醒。":
            bad(f"解说词解析错误：{shots[0].narration}")
        else:
            ok("解说词解析正确")
        if abs(shots[1].end - 9.8) > 0.01:
            bad(f"时间轴解析错误：{shots[1].end}")
        else:
            ok("时间轴解析正确")
        if usage.units != 1234:
            bad(f"用量统计错误：{usage.units}")
        else:
            ok(f"用量统计正确（{usage.units} tokens）")
        body = json.loads(captured["body"])
        has_image = any("inline_data" in p for p in body["contents"][0]["parts"])
        if frames and not has_image:
            bad("请求中没有带上关键帧")
        else:
            ok("请求携带关键帧")
        if "responseMimeType" not in json.dumps(body):
            bad("请求未要求 JSON 输出")
        else:
            ok("请求声明 JSON 输出")
    finally:
        restore()


async def test_openai_compat() -> None:
    print("\n[OpenAI 兼容 · 抽帧]")
    captured: dict = {}

    def responder(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "```json\n" + json.dumps(SHOT_JSON, ensure_ascii=False) + "\n```"}}],
                "usage": {"total_tokens": 888},
            },
        )

    install(responder)
    try:
        provider = get_vision("openai")
        frames_dir = ROOT / "data" / "selftest" / "frames"
        frames = [FrameSample(t, p) for t, p in [(1.0, frames_dir / "f_0000.jpg")] if p.exists()]
        req = AnalysisRequest(
            video_path=None,
            frames=frames,
            duration=12.0,
            style="story",
            key="sk-fake",
            model="gpt-4o",
        )
        shots, usage = await provider.analyze(req)
        if len(shots) != 2:
            bad(f"应解析出 2 个镜头，实际 {len(shots)}")
        else:
            ok(f"解析出 {len(shots)} 个镜头（已处理 markdown 围栏）")
        if usage.units != 888:
            bad(f"用量统计错误：{usage.units}")
        else:
            ok(f"用量统计正确（{usage.units} tokens）")
        body = json.loads(captured["body"])
        if body.get("response_format", {}).get("type") != "json_object":
            bad("未请求 JSON 模式")
        else:
            ok("请求使用 json_object 模式")
        content = body["messages"][-1]["content"]
        has_image = any(c.get("type") == "image_url" for c in content)
        if frames and not has_image:
            bad("请求中没有带上图片")
        else:
            ok("请求携带图片（data URL）")
        if "chat/completions" not in captured["url"]:
            bad(f"端点不正确：{captured['url']}")
        else:
            ok(f"端点正确：{captured['url']}")
    finally:
        restore()


async def test_qwen() -> None:
    print("\n[通义千问 · 百炼多模态]")
    captured: dict = {}

    def responder(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [{"text": json.dumps(SHOT_JSON, ensure_ascii=False)}]
                            }
                        }
                    ]
                },
                "usage": {"total_tokens": 555},
            },
        )

    install(responder)
    try:
        provider = get_vision("qwen")
        frames_dir = ROOT / "data" / "selftest" / "frames"
        frames = [FrameSample(t, p) for t, p in [(1.0, frames_dir / "f_0000.jpg")] if p.exists()]
        req = AnalysisRequest(
            video_path=None, frames=frames, duration=12.0, style="emotion", key="sk-fake", model="qwen-vl-max"
        )
        shots, usage = await provider.analyze(req)
        if len(shots) != 2:
            bad(f"应解析出 2 个镜头，实际 {len(shots)}")
        else:
            ok(f"解析出 {len(shots)} 个镜头")
        if usage.units != 555:
            bad(f"用量统计错误：{usage.units}")
        else:
            ok(f"用量统计正确（{usage.units} tokens）")
        body = json.loads(captured["body"])
        content = body["input"]["messages"][0]["content"]
        if not any("image" in c for c in content):
            bad("请求中没有带上图片")
        else:
            ok("请求携带图片")
        if "multimodal-generation" not in captured["url"]:
            bad(f"端点不正确：{captured['url']}")
        else:
            ok("端点为百炼多模态生成接口")
    finally:
        restore()


async def test_error_handling() -> None:
    print("\n[错误处理]")
    install(lambda r: httpx.Response(401, json={"error": {"message": "API key not valid"}}))
    try:
        provider = get_vision("gemini")
        req = AnalysisRequest(video_path=None, frames=[], duration=10, style="cinematic", key="bad", model="gemini-2.5-flash")
        try:
            await provider.analyze(req)
            bad("401 应抛出 ProviderError")
        except ProviderError as exc:
            ok(f"401 转换为可读错误：{str(exc)[:70]}...")
    finally:
        restore()

    install(lambda r: httpx.Response(200, text="这不是 JSON"))
    try:
        provider = get_vision("openai")
        req = AnalysisRequest(video_path=None, frames=[], duration=10, style="cinematic", key="k", model="gpt-4o")
        try:
            await provider.analyze(req)
            bad("非 JSON 返回应抛出 ProviderError")
        except ProviderError as exc:
            ok(f"非 JSON 返回转换为可读错误：{str(exc)[:60]}")
    finally:
        restore()


async def test_alignment() -> None:
    print("\n[镜头对齐]")
    from app.services.pipeline import _align_shots
    from ai_providers.base import ShotDraft

    bounds = [(0.0, 4.0), (4.0, 8.0), (8.0, 12.0)]
    drafts = [
        ShotDraft(0.0, 5.0, visual="A", narration="第一段"),
        ShotDraft(5.0, 12.0, visual="B", narration="第二段"),
    ]
    aligned = _align_shots(bounds, drafts)
    if len(aligned) != 3:
        bad(f"对齐后应有 3 个镜头，实际 {len(aligned)}")
        return
    ok(f"对齐后 {len(aligned)} 个镜头（以本地时间轴为准）")
    if aligned[0]["narration"] != "第一段":
        bad("镜头 1 映射错误")
    else:
        ok("镜头 1 映射到重叠最大的模型片段")
    if aligned[2]["narration"] != "第二段":
        bad("镜头 3 映射错误")
    else:
        ok("镜头 3 映射到重叠最大的模型片段")


async def main() -> int:
    await test_gemini()
    await test_openai_compat()
    await test_qwen()
    await test_error_handling()
    await test_alignment()
    print()
    if failures:
        print(f"{RED}失败 {len(failures)} 项{RESET}")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"{GREEN}全部通过{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
