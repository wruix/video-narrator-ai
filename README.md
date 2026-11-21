<div align="center">

# VideoNarrator AI

**AI Video Narration Workstation** — multi-model, bilingual, cross-platform.

> **Status: 1.0.0 Release Candidate.** This is the open-core source code. The build and
> the Windows frozen-backend smoke are CI-verified; a public downloadable installer and
> full customer-environment acceptance are **not yet released**. See
> [Release notes](#release-status) below.

[English](README.md) · [简体中文](README.zh-CN.md) · [许可与边界](LICENSING.md) · [贡献指南](CONTRIBUTING.md)

</div>

---

Turn any video into a narrated, subtitled, voice-overed short — with shot-by-shot
scripts you can review and edit before a single frame is rendered.

- **Multi-model** — Gemini (native video upload), Qwen Omni, Doubao/Ark, OpenAI, SiliconFlow, or a local Ollama/vLLM server
- **Pluggable voice** — Microsoft Edge voices (free), OpenAI, Azure Speech, ElevenLabs, or your own endpoint
- **Human in the loop** — automatic checks, per-shot editing, single-line rewrite, lock, approve
- **Bilingual UI** — 简体中文 / English, independent from the narration language
- **Desktop & web** — one codebase, an Electron shell for Windows/macOS/Linux and a FastAPI service for the web

---

## Table of contents

- [What it does](#what-it-does)
- [Screens](#screens)
- [Quick start](#quick-start)
- [Deploying](#deploying)
- [Repository layout](#repository-layout)
- [How the pipeline works](#how-the-pipeline-works)
- [Configuration](#configuration)
- [Tiers & quotas](#tiers--quotas)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [Release status](#release-status)
- [License](#license)

---

## What it does

1. **Import** a video — duration, resolution and the original audio track are read on arrival.
2. **Choose models and style** — which model understands the video, which one rewrites the copy, what narration style, what aspect ratio, which voice.
3. **Review the script** — the workstation splits the video into shots, extracts keyframes, has the model describe each shot and draft a line of narration. You edit, rewrite or lock each line, and the automatic checks tell you when the voice-over will outrun the picture.
4. **Generate** — per-line speech synthesis, timeline layout, SRT subtitles, mixed audio (narration over the ducked original), burned-in subtitles, and a final MP4.

Everything runs on your own machine. Video never leaves the box.

---

## Screens

| Step | What you get |
| --- | --- |
| ① Video input | Drag-and-drop import, immediate probe of duration/resolution/audio, live preview |
| ② Models & creative settings | Analysis model, copywriter model, ASR, voice service, output ratio, six narration styles, voice / speed / emotion, **narration language** (independent of the UI language) |
| ③ Script editor & preview | Video on the left, shot list on the right: keyframe thumbnails, editable narration, emotion & speed per shot, one-click rewrite, lock. Automatic checks for empty lines, character count and narration-to-video ratio |
| ④ Generate & export | Per-shot TTS → timeline → SRT → mixed MP4, with a render history you can preview and download |

---

## Quick start

### Requirements

| Component | Version | Notes |
| --- | --- | --- |
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Only to build the frontend |
| FFmpeg | 9.0.2 | Must include `ffmpeg` **and** `ffprobe`; pinned to the locked 9.0.2 builds in `config/ffmpeg-assets-lock.md` (see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the GPL license text that must accompany any bundled binary) |

```bash
# Debian / Ubuntu
sudo apt install ffmpeg fonts-noto-cjk
# macOS
brew install ffmpeg
# Windows (9.0.2 pinned build, matches config/ffmpeg-assets-lock.md)
winget install --id Gyan.FFmpeg  # or download the pinned 9.0.2 package from https://www.gyan.dev/ffmpeg/builds/packages/
```

`fonts-noto-cjk` matters on Linux: without a CJK font, burned-in subtitles render as boxes.

### Install and run

```bash
git clone https://github.com/your-org/video-narrator-ai.git
cd video-narrator-ai

# Windows
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\start.ps1

# Linux / macOS
./scripts/start.sh
```

Then open <http://127.0.0.1:8080>.

### Add an API key

Click **Settings & API keys** and paste a key for the model you want to use.
Keys are encrypted with Fernet on the server; the browser only ever receives a mask
(`sk-t******7890`). A GitHub repo without a licence is not open source — this repo ships
with [Apache-2.0](LICENSE).

Edge voice needs no key at all, so you can exercise the whole pipeline before signing up
for anything.

---

## Deploying

### Desktop (Windows / macOS / Linux)

Build the desktop shell locally (a public downloadable installer is **not yet
published**; see [Release status](#release-status)):

```bash
npm install
npm run build:web
npm run build:desktop
cd apps/desktop && npm start
```

### Web (self-hosted)

```bash
cp config/tiers.example.yaml config/tiers.yaml   # edit to taste
cp deploy/docker-compose.yml .
VC_ACCESS_TOKEN="$(openssl rand -hex 24)" docker compose up -d
```

Or without Docker:

```bash
./scripts/start.sh 0.0.0.0 8080
```

> **Before exposing it to anyone else**, set `VC_ACCESS_TOKEN`, put it behind an HTTPS
> reverse proxy, and switch to platform-managed keys. See
> [Deploying](docs/en/deployment.md) for the full checklist.

---

## Repository layout

```
video-narrator-ai/
├── apps/
│   ├── web/                    # React + TypeScript frontend
│   └── desktop/                # Electron shell (Win / mac / Linux)
├── services/
│   └── api/                    # FastAPI service
├── packages/
│   ├── ui/                     # Shared React components
│   ├── i18n/                   # zh-CN / en resources
│   ├── ai-providers/           # Model & TTS adapters
│   └── media-core/             # FFmpeg, shot detection, keyframes, subtitles, composition
├── deploy/                     # Dockerfile + docker-compose
├── docs/{en,zh-CN}/            # Documentation
├── config/tiers.yaml           # Quotas & pricing — never hardcoded in code
└── .github/workflows/           # CI + cross-platform release builds
```

The dependency direction is strictly one-way:

```
apps/web ──▶ packages/ui, packages/i18n
                    │
services/api ──▶ packages/ai-providers ──▶ packages/media-core
```

`packages/media-core` knows nothing about any model vendor. `packages/ai-providers`
knows nothing about FastAPI or the database. That is what makes swapping models cheap.

---

## How the pipeline works

```
probe → shots → frames → asr → analyze → script → review(manual) → tts → subtitle → compose
```

| Stage | Detail |
| --- | --- |
| `probe` | ffprobe reads duration, resolution, fps, audio presence |
| `shots` | `scdet` scene detection → shot boundaries, long shots split, very short tails merged |
| `frames` | Keyframes per shot; frame-to-frame diffing spots fast motion and adds intermediate frames so action is not missed |
| `asr` | Optional speech recognition so the model understands the original dialogue |
| `analyze` | The vision model returns a structured shot list: visual description, draft narration, dialogue, emotion |
| `script` | Optional second pass with the copywriter model rewrites each line into the chosen style |
| `review` | **Blocks here.** You edit, rewrite, lock, approve. |
| `tts` | Per-line speech synthesis, laid out on the original timeline |
| `subtitle` | SRT built from the *actual* synthesised durations, so subtitles stay in sync |
| `compose` | ffmpeg: scale/crop to the target ratio, mix narration over the ducked original, burn subtitles, encode MP4 |

---

## Configuration

Everything is optional; every value has a default. See `services/api/.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VC_DATA_DIR` | `./data` | Uploads, working files, renders, database |
| `VC_FFMPEG` / `VC_FFPROBE` | `ffmpeg` / `ffprobe` | Explicit binary paths |
| `VC_MASTER_KEY` | generated | Key-encryption master key; changing it invalidates stored keys |
| `VC_ACCESS_TOKEN` | *(disabled)* | Requires a token on every endpoint — **set this when deploying** |
| `VC_CORS_ORIGINS` | `*` | Comma-separated allow-list |
| `VC_SERVER_KEY_<PROVIDER>` | — | Platform-managed keys (Mode B) |
| `VC_SCENE_THRESHOLD` | `0.28` | Shot detection sensitivity (lower = finer) |
| `VC_FRAME_INTERVAL` | `2.0` | Fallback keyframe interval in seconds |
| `VC_MAX_UPLOAD_MB` | `4096` | Global upload ceiling (per-tier caps apply too) |
| `VC_SUBTITLE_FONT` | platform default | Font used for burned-in subtitles |
| `VC_TIERS_FILE` | `config/tiers.yaml` | Which tier configuration to load |

---

## Tiers & quotas

Quotas and prices live in `config/tiers.yaml` — **never in code**. Model prices change;
your pricing shouldn't require a release.

```yaml
tiers:
  free:
    upload_max_mb: 512
    monthly_video_seconds: 300
    concurrent_jobs: 1
    byok: false
```

`VC_TIER` selects the active tier for a self-hosted instance; the cloud deployment
resolves it from the account.

---

## Testing

```bash
powershell -ExecutionPolicy Bypass -File scripts\test-all.ps1   # Windows
./scripts/test-all.sh                                           # Linux / macOS
```

| Suite | What it covers | Needs network? |
| --- | --- | --- |
| `scripts/selftest.py` | Media pipeline end to end: synthesises a test video, detects shots, extracts frames, synthesises speech, builds subtitles, renders an MP4 | Edge TTS only |
| `scripts/test_providers.py` | Provider adapters with stubbed responses: request shape, JSON parsing, shot alignment, error handling | No |
| `scripts/api_test.py` | The HTTP API end to end over a live server | No |
| `scripts/check_key_storage.py` | Keys are ciphertext at rest, no plaintext leakage | No |

CI runs the Python suites on Linux, macOS and Windows, and type-checks and builds the
frontend on every push.

---

## Roadmap

- [x] Multi-model adapter layer with native-video support for Gemini
- [x] Shot detection, adaptive keyframe extraction, subtitle timing calibration
- [x] Human review step with per-shot editing and automatic checks
- [x] Bilingual UI, narration language independent from interface language
- [x] Monorepo with reusable `media-core` and `ai-providers` packages
- [x] Electron desktop shell for Windows / macOS / Linux
- [x] Open-Core licensing and a configuration-driven tier system
- [ ] Accounts, teams and shared projects for the hosted service
- [ ] Batch jobs and a standalone worker with a real task queue
- [ ] Per-shot clip export and timeline editing
- [ ] More narration languages and more TTS voices

---

## License

Apache-2.0 — see [LICENSE](LICENSE).

This repository is the **open core**. The hosted VideoNarrator AI service is a separate,
proprietary product that talks to this code over its public API; see
[LICENSING.md](LICENSING.md) for exactly where the boundary sits and what would change
if you want to restrict closed-source hosting later.

Third-party components and their licences: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## Release status

**VideoNarrator AI 1.0.0 — Release Candidate (open source code).**

- **What is public here:** the open-core source code under Apache-2.0, plus the locked
  asset manifests and CI workflow. No compiled installer artifact is published here.
- **Verified:** cross-platform builds and the Windows frozen-backend smoke are
  CI-verified (GitHub Actions, release-candidate/ra-15).
- **Not yet done:**
  - A public, downloadable installer (GitHub Actions artifact upload is blocked by an
    account-level storage quota, so no Release artifact exists yet).
  - Full customer-environment / end-to-end acceptance.
- **You configure your own AI providers** — this project ships **no API keys**.
  Add your own keys via Settings (they are encrypted at rest; the browser only sees a
  mask). Some TTS/voice services (e.g. Microsoft Edge TTS) need no key at all.
- **FFmpeg:** the repo does **not** bundle FFmpeg binaries; CI downloads the pinned
  9.0.2 builds per `config/ffmpeg-assets-lock.md`. If you build an installer that ships
  those FFmpeg binaries, you must attach their GPL license text and source availability
  (see THIRD_PARTY_NOTICES.md) — the GPL obligations apply to that installer, not to this
  source repository.
