# @vns/ai-providers

Pluggable adapters for video understanding, copywriting and text-to-speech.

Each vendor implements the same small surface, so the pipeline never branches on
provider identity:

```python
class MyProvider:
    spec = ProviderSpec(id="myvendor", name="My Vendor", kind="vision", ...)

    async def analyze(self, req: AnalysisRequest) -> tuple[list[ShotDraft], Usage]: ...
    async def complete(self, req: TextRequest) -> tuple[str, Usage]: ...
    async def test(self, key: str) -> dict: ...
```

Register it in `ai_providers/__init__.py` and it appears in the UI automatically.

## Included

| id | Vendor | Native video | Notes |
| --- | --- | --- | --- |
| `gemini` | Google Gemini | ✅ | Whole-video upload via the Files API; falls back to keyframes |
| `qwen` | 通义千问 / Qwen Omni | keyframes | DashScope multimodal endpoint |
| `doubao` | 豆包 / 火山方舟 | keyframes | Ark OpenAI-compatible endpoint |
| `openai` | OpenAI | keyframes | Chat Completions with image inputs |
| `siliconflow` | 硅基流动 | keyframes | |
| `ollama` | Local Ollama / vLLM | keyframes | No key required |
| `edge`, `edge-lite` | Microsoft Edge TTS | — | Free, no key |
| `openai-tts`, `azure-tts`, `elevenlabs`, `custom-tts` | Various TTS | — | |

## Rules for new adapters

1. Use the shared `http_client()` helper — it turns network failures into actionable
   messages and honours `HTTP_PROXY` / `HTTPS_PROXY`.
2. Parse results with `extract_json()`; it tolerates markdown fences and surrounding prose.
3. Raise `ProviderError` with a message a user can act on. Never let a raw `httpx`
   exception escape.
4. Report token usage via the returned `Usage` object so the usage screen stays accurate.
5. Add a stubbed case to `scripts/test_providers.py`.

## Licence

Apache-2.0, same as the parent repository.
