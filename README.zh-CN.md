<div align="center">

# VideoNarrator AI

**AI 视频解说工作站** —— 多模型、可切换、双语、跨平台。

[English](README.md) · [简体中文](README.zh-CN.md) · [许可与边界](LICENSING.md) · [贡献指南](CONTRIBUTING.md)

</div>

---

把任意视频变成有解说、有配音、有字幕的成片——逐镜头文案在渲染之前由你审核和修改。

- **多模型**：Gemini（原生整段视频上传）、通义千问 Omni、豆包/火山方舟、OpenAI、硅基流动，或本地 Ollama / vLLM
- **可换配音**：Microsoft Edge 语音（免费）、OpenAI、Azure 语音、ElevenLabs，或自定义端点
- **人工在环**：自动检查、逐镜头改写、单句重写、锁定、审核通过
- **中英双语**：界面语言与解说词语言相互独立
- **桌面 + 网页**：同一套代码，Electron 外壳覆盖 Windows/macOS/Linux，FastAPI 服务承载网页版

---

## 目录

- [它能做什么](#它能做什么)
- [四个步骤](#四个步骤)
- [快速开始](#快速开始)
- [部署](#部署)
- [仓库结构](#仓库结构)
- [流水线是怎么跑的](#流水线是怎么跑的)
- [配置](#配置)
- [套餐与额度](#套餐与额度)
- [测试](#测试)
- [路线图](#路线图)
- [许可证](#许可证)

---

## 它能做什么

1. **导入视频**——上传后立刻读出时长、分辨率与原始音轨。
2. **选模型与风格**——谁来看懂视频、谁来改写文案、解说风格、输出比例、用哪个音色。
3. **审核文案**——工作站切分镜头、抽取关键帧，让模型逐镜头描述并起草解说。你逐句修改、重写、锁定；自动检查会提醒你解说会不会比画面长。
4. **生成成片**——逐句配音、按时间轴排布、生成 SRT 字幕、解说与压低后的原声混音、烧录字幕、输出 MP4。

全部在本机完成，视频不出你的机器。

---

## 四个步骤

| 步骤 | 内容 |
| --- | --- |
| ① 视频输入 | 拖拽导入，上传即探测时长/分辨率/音轨，实时预览 |
| ② 模型与创作设置 | 分析模型、文案模型、语音识别、配音服务、输出比例、六种解说风格、音色/语速/情绪，以及**解说词语言**（与界面语言独立） |
| ③ 解说编辑与预览 | 左视频右镜头：关键帧缩略图、可编辑解说词、逐镜头情绪与语速、单句重写、锁定；自动检查空文案、字数与解说/画面时长比 |
| ④ 一键生成与导出 | 逐句配音 → 时间轴 → SRT → 混音 MP4，成片历史可预览可下载 |

---

## 快速开始

### 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.11+ | 后端运行时 |
| Node.js | 18+ | 仅构建前端时需要 |
| FFmpeg | 6.0+ | 必须同时包含 `ffmpeg` 与 `ffprobe` |

```bash
# Debian / Ubuntu
sudo apt install ffmpeg fonts-noto-cjk
# macOS
brew install ffmpeg
# Windows
winget install --id BtbN.FFmpeg.GPL.8.1 --exact
```

Linux 上 `fonts-noto-cjk` 很重要：没有中文字体，烧录的字幕会变成方块。

### 安装与启动

```bash
git clone https://github.com/your-org/video-narrator-ai.git
cd video-narrator-ai

# Windows
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\start.ps1

# Linux / macOS
./scripts/start.sh
```

然后打开 <http://127.0.0.1:8080>。

### 填 API Key

点击右上角「设置与密钥」填入你要用的模型 Key。密钥在服务端用 Fernet 加密存储，
浏览器只会拿到掩码（`sk-t******7890`）。

Edge 语音完全不需要 Key，所以你在注册任何平台之前就能把整条链路跑通。

> GitHub 仓库如果没有选择许可证，代码并不自动成为开源软件——本仓库采用
> [Apache-2.0](LICENSE)，从第一天就定好了。

---

## 部署

### 桌面版（Windows / macOS / Linux）

从 Releases 下载安装包。桌面外壳会启动本机 Python 后端并把窗口指向它——
界面与网页版完全一致。

```bash
npm install
npm run build:web
npm run build:desktop
cd apps/desktop && npm start
```

### 网页版（自建）

```bash
cp config/tiers.example.yaml config/tiers.yaml   # 按需修改
cp deploy/docker-compose.yml .
VC_ACCESS_TOKEN="$(openssl rand -hex 24)" docker compose up -d
```

不用 Docker：

```bash
./scripts/start.sh 0.0.0.0 8080
```

> **暴露给其他人之前**，务必设置 `VC_ACCESS_TOKEN`、套一层 HTTPS 反向代理、
> 并改用平台托管 Key。完整清单见 [部署文档](docs/zh-CN/deployment.md)。

---

## 仓库结构

```
video-narrator-ai/
├── apps/
│   ├── web/                    # React + TypeScript 前端
│   └── desktop/                # Electron 外壳（Win / mac / Linux）
├── services/
│   └── api/                    # FastAPI 服务
├── packages/
│   ├── ui/                     # 共享 React 组件
│   ├── i18n/                   # 中英文案资源
│   ├── ai-providers/           # 模型与配音适配器
│   └── media-core/             # FFmpeg、镜头切分、关键帧、字幕、合成
├── deploy/                     # Dockerfile + docker-compose
├── docs/{zh-CN,en}/            # 文档
├── config/tiers.yaml           # 额度与价格——绝不写死在代码里
└─ .github/workflows/           # CI 与跨平台打包
```

依赖方向严格单向：

```
apps/web ──▶ packages/ui, packages/i18n
                    │
services/api ──▶ packages/ai-providers ──▶ packages/media-core
```

`packages/media-core` 不知道任何模型厂商；`packages/ai-providers` 不知道 FastAPI 与数据库。
这就是以后换模型不用重写整个软件的原因。

---

## 流水线是怎么跑的

```
probe → shots → frames → asr → analyze → script → review(人工) → tts → subtitle → compose
```

| 阶段 | 细节 |
| --- | --- |
| `probe` | ffprobe 读取时长、分辨率、帧率、有无音轨 |
| `shots` | `scdet` 场景检测 → 镜头边界；过长镜头拆分，过短尾巴合并 |
| `frames` | 逐镜头抽帧；用帧间差异识别快速运动区间并补抽中间帧，避免漏掉关键动作 |
| `asr` | 可选语音识别，让模型理解原声对白 |
| `analyze` | 视觉模型返回结构化镜头列表：画面描述、解说初稿、对白、情绪 |
| `script` | 可选二次创作：文案模型按选定风格逐句改写 |
| `review` | **在这里停下**，由你改写、重写、锁定、审核通过 |
| `tts` | 逐句合成配音，按原始时间轴排布 |
| `subtitle` | 用**实际合成时长**生成 SRT，字幕自然对齐 |
| `compose` | ffmpeg：缩放/裁切到目标比例、解说与压低后的原声混音、烧录字幕、编码 MP4 |

---

## 配置

全部可选，都有默认值。完整清单见 `services/api/.env.example`。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `VC_DATA_DIR` | `./data` | 上传素材、工作文件、成片、数据库 |
| `VC_FFMPEG` / `VC_FFPROBE` | `ffmpeg` / `ffprobe` | 可执行文件绝对路径 |
| `VC_MASTER_KEY` | 自动生成 | 密钥加密主密钥；更换后已存密钥无法解密 |
| `VC_ACCESS_TOKEN` | *（不启用）* | 所有接口都需要口令——**部署时务必设置** |
| `VC_CORS_ORIGINS` | `*` | 逗号分隔的来源白名单 |
| `VC_SERVER_KEY_<厂商>` | — | 平台托管 Key（模式 B） |
| `VC_SCENE_THRESHOLD` | `0.28` | 镜头切分灵敏度（越小切得越细） |
| `VC_FRAME_INTERVAL` | `2.0` | 兜底抽帧间隔（秒） |
| `VC_MAX_UPLOAD_MB` | `4096` | 全局上传上限（同时受套餐上限约束） |
| `VC_SUBTITLE_FONT` | 按平台默认 | 烧录字幕使用的字体 |
| `VC_TIERS_FILE` | `config/tiers.yaml` | 加载哪一份套餐配置 |

---

## 套餐与额度

额度与价格写在 `config/tiers.yaml`——**绝不写死在代码里**。模型涨价时，
你的定价策略不该跟着发版。

```yaml
tiers:
  free:
    upload_max_mb: 512
    monthly_video_seconds: 300
    concurrent_jobs: 1
    byok: false
```

自建实例通过 `VC_TIER` 选择生效档位；云端部署则由账号决定。

---

## 测试

```bash
powershell -ExecutionPolicy Bypass -File scripts\test-all.ps1   # Windows
./scripts/test-all.sh                                           # Linux / macOS
```

| 套件 | 覆盖内容 | 需要联网 |
| --- | --- | --- |
| `scripts/selftest.py` | 媒体链路端到端：合成测试视频 → 镜头切分 → 抽帧 → 配音 → 字幕 → 合成 MP4 | 只需 Edge TTS |
| `scripts/test_providers.py` | 用打桩响应验证模型适配层：请求构造、JSON 解析、镜头对齐、错误处理 | 否 |
| `scripts/api_test.py` | 对着运行中的服务跑完整 HTTP 接口 | 否 |
| `scripts/check_key_storage.py` | 密钥在库中是密文、无明文泄漏 | 否 |

CI 会在 Linux、macOS、Windows 上跑 Python 测试，并对前端做类型检查与构建。

---

## 路线图

- [x] 多模型适配层，Gemini 支持原生视频上传
- [x] 镜头切分、自适应抽帧、字幕时间轴校准
- [x] 人工审核环节：逐镜头编辑 + 自动检查
- [x] 中英双语界面，解说语言与界面语言独立
- [x] Monorepo，抽出可复用的 `media-core` 与 `ai-providers`
- [x] Windows / macOS / Linux 的 Electron 桌面端
- [x] Open-Core 许可证与配置化套餐体系
- [ ] 云端账号、团队协作与共享项目
- [ ] 批量任务与独立 Worker + 真正的任务队列
- [ ] 分镜片段导出与时间轴编辑
- [ ] 更多解说语言与更多音色

---

## 许可证

Apache-2.0，见 [LICENSE](LICENSE)。

本仓库是**开源核心**。官方托管的 VideoNarrator AI 服务是另一个独立闭源产品，
通过公开 API 与本代码交互；边界具体划在哪里、以后若要限制第三方闭源部署需要改什么，
见 [LICENSING.md](LICENSING.md)。

第三方组件与其许可证：[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
