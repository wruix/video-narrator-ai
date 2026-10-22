# Contributing to VideoNarrator AI

Thanks for helping out. This document covers how to get set up, what we expect from a
pull request, and the couple of rules that keep the open-core boundary intact.

中文版本：[CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)

---

## 1. Getting set up

```bash
git clone https://github.com/your-org/video-narrator-ai.git
cd video-narrator-ai

# Windows
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Linux / macOS
./scripts/start.sh
```

You need Python 3.11+, Node.js 18+ and FFmpeg (with `ffprobe`). See the README for
platform-specific install commands.

Run the tests before you change anything, so you know the baseline:

```bash
powershell -ExecutionPolicy Bypass -File scripts\test-all.ps1   # Windows
./scripts/test-all.sh                                           # Linux / macOS
```

---

## 2. Where to put your code

The dependency direction is one-way and must stay that way:

```
apps/web ──▶ packages/ui, packages/i18n
                    │
services/api ──▶ packages/ai-providers ──▶ packages/media-core
```

| If you are… | Put it in | Do not |
| --- | --- | --- |
| Adding a model vendor | `packages/ai-providers/` | Import `fastapi` or `sqlalchemy` there |
| Changing video processing | `packages/media-core/` | Import a model vendor there |
| Adding UI text | `packages/i18n/src/locales/` | Hardcode a Chinese string in a component |
| Adding a page or component | `apps/web/src/components/` | Put business logic in the component |
| Adding an HTTP endpoint | `services/api/app/routers/` | Talk to the database outside a router |

**The most important rule:** `packages/media-core` must never import a model vendor,
and `packages/ai-providers` must never import FastAPI or the database. That separation
is what makes swapping models cheap, and it is what keeps the open-core boundary clean.

---

## 3. Adding a model vendor

1. Create `packages/ai-providers/ai_providers/<vendor>.py`.
2. Implement the same shape as the existing providers:

   ```python
   class MyProvider:
       spec = ProviderSpec(
           id="myvendor",
           name="My Vendor",
           kind="vision",
           default_model="my-model",
           models=["my-model"],
           key_hint="Where to get a key",
           native_video=False,
       )

       async def analyze(self, req: AnalysisRequest) -> tuple[list[ShotDraft], Usage]: ...
       async def complete(self, req: TextRequest) -> tuple[str, Usage]: ...
       async def test(self, key: str) -> dict: ...
   ```

3. Register it in `packages/ai-providers/ai_providers/__init__.py`.
4. Add a case to `scripts/test_providers.py` with a stubbed response.
5. Add the display name to `packages/i18n/src/locales/{zh-CN,en}.ts` under `providers`.

The provider must be resilient: raise `ProviderError` with a message a user can act on,
and never let a raw `httpx` exception escape. Use the shared `http_client()` helper so
network failures produce a readable message.

---

## 4. Adding UI text

Both locales must stay in sync — the type checker enforces the key structure.

```bash
# packages/i18n/src/locales/zh-CN.ts
export const zhCN = {
  mySection: {
    myKey: "中文",
  },
} as const;
```

```bash
# packages/i18n/src/locales/en.ts
export const en: TranslationSchema = {
  mySection: {
    myKey: "English",
  },
};
```

Then use it:

```tsx
const { t } = useTranslation();
<span>{t("mySection.myKey")}</span>
```

**The interface language and the narration language are separate things.** Do not
conflate them: a Chinese interface may generate an English voice-over.

---

## 5. Style

- Python: 110-column lines, `ruff check --select E,W,F` clean, type hints on public functions.
- TypeScript: `strict` mode, no `any` unless you justify it, `npm run typecheck` clean.
- Comments explain *why*, not *what*. Write them in the same language as the surrounding code.
- User-facing strings go through i18n. User-facing **error messages** from the backend
  should be actionable ("check your network or set HTTP_PROXY"), not raw exceptions.

---

## 6. Pull requests

- One logical change per PR.
- Add or update tests. A new provider needs a `scripts/test_providers.py` case; a bug fix
  needs a regression test.
- Update `README.md` **and** `README.zh-CN.md` if you change user-visible behaviour.
- Update `THIRD_PARTY_NOTICES.md` if you add a dependency.
- Update `docs/{en,zh-CN}/` if you change configuration or deployment.

---

## 7. The open-core boundary

This repository is Apache-2.0 and stays open source. The hosted service is proprietary
and lives in a separate repository.

**Do not merge** code that:

- implements accounts, billing, metering or tenant isolation,
- embeds the hosted service's proprietary orchestration,
- pulls in code under a licence incompatible with Apache-2.0.

Features that belong to the hosted service should be expressed as extensions to this
repository's public API, implemented in the proprietary repository.

If you are unsure whether a change crosses the line, open an issue and ask first.

---

## 8. Licensing changes

Changing the licence of this repository — in whole or in part — is a **one-way door**
once outside contributions exist. Any such change requires maintainer sign-off and a
note in the changelog. See [LICENSING.md](LICENSING.md).

---

## 9. Reporting bugs

Use the issue templates. A good report includes:

- your OS, Python and FFmpeg versions,
- the model and TTS service involved,
- what you expected versus what happened,
- the relevant part of `data/logs/app.log` (it contains stack traces for unhandled errors).

Please redact any API keys before pasting logs.

---

## 10. Code of conduct

Be decent to each other. Assume good faith, critique the code rather than the person,
and help newcomers get their first PR merged.
