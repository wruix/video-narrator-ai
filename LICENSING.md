# Licensing & Open-Core Boundary

> 许可证与开源治理说明。**发布前请让专业律师过一遍**，本文档不是法律意见。

## 1. 本仓库的许可证

本仓库（`video-narrator-ai`）全部内容采用 **Apache License 2.0**，见 [`LICENSE`](./LICENSE)。

选择 Apache-2.0 的原因：

- 允许他人基于本项目做商业集成，SaaS 厂商可以基于它提供服务而不必开源自己的代码；
- 专利授权条款对采用方更友好；
- 被 Electron / FastAPI / React 生态大量使用，法律文本成熟、争议少。

## 2. Open-Core 边界

```
┌────────────────────────────────────────────────────────────┐
│  本仓库（Apache-2.0）                                        │
│  apps/desktop      桌面端外壳                                 │
│  apps/web          网页端前端                                 │
│  packages/ui       共享 UI 组件                               │
│  packages/i18n     双语资源                                  │
│  packages/media-core  视频处理内核（FFmpeg 封装、抽帧、字幕）   │
│  packages/ai-providers  模型适配器（Gemini/Qwen/豆包/OpenAI…） │
│  services/api      自建服务（FastAPI）                        │
├──────────────────────────────────────────────────────────────┤
│  官方云服务（闭源，私有仓库）                                  │
│  · 托管算力与存储                                              │
│  · 用量计量与订阅计费                                          │
│  · 团队协作、成员权限                                          │
│  · 批量任务与调度                                              │
│  · 官方运维与 SLA                                             │
└──────────────────────────────────────────────────────────────┘
```

边界靠**仓库隔离 + API 契约**保证，而不是靠目录命名或许可证技巧：

- 闭源部分通过 HTTP 调用本仓库的公开 API，不链接、不修改核心代码；
- Apache-2.0 明确允许闭源 SaaS 基于其构建商业服务；
- 本仓库不包含任何计费、客户数据、编排与运维代码。

## 3. 商业化路径

| 版本 | 用户获得 | 商业模式 |
| --- | --- | --- |
| Desktop Community | 本地处理、自带 Key、字幕/配音/合成、项目管理 | 免费开源 |
| Web Community | 自行部署整个仓库 | 免费开源 |
| Web Free | 官方云端限额体验 | 免费额度 |
| Web Pro | 更高用量、批量处理、云端存储 | 订阅 |
| Web Team | 团队协作、共享项目、成员权限 | 团队订阅 |
| Enterprise | 私有部署、定制工作流、合规配置、技术支持 | 商业报价 |

## 4. 免费额度不要写死在代码里

额度、定价、模型单价一律来自 `config/tiers.yaml`（示例见 `config/tiers.example.yaml`），
通过环境变量 `VC_TIERS_FILE` 指定。这样模型涨价或换供应商时，改配置即可，不必发版。

## 5. 如果将来想限制「第三方闭源部署」

当前 Apache-2.0 **允许**他人闭源部署你的服务。如果将来希望「提供网络服务的修改版必须开源」，
可选路径是把 `services/api`（服务端）单独改为 **AGPL-3.0**：

- AGPL-3.0 同样允许商业使用和收费，**不是**禁止商业运营的许可证；
- 它增加的是：通过网络提供服务时，必须向使用者提供对应修改版源码；
- 影响面：`services/api` 依赖 `packages/ai-providers`（Apache-2.0），
  组合后的整体按 AGPL 处理；`apps/desktop` 若不内嵌服务端代码则不受影响。

**这是一条单向路**：一旦有人基于 AGPL 版本贡献代码，就不能再改回 Apache-2.0。
因此在仓库公开、有人提交 PR 之前就应当决定。

本项目当前不内置账号系统与多租户隔离，因此不构成 AGPL 意义上的「修改版对外提供服务」。
一旦加入多租户 SaaS 能力，请重新评估。

## 6. 第三方组件与合规

- **FFmpeg**：本项目**不分发** FFmpeg 二进制，只在运行时调用用户自行安装的 FFmpeg。
  如果你在安装包里附带 FFmpeg，必须同时附带其 `LICENSE.md` / `COPYING.LGPLv3` 等许可文件，
  并根据实际启用的编解码器判断是 LGPL 还是 GPL。详见 [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md)。
- **Microsoft Edge TTS**：通过 `edge-tts` 调用微软公开的 Edge 朗读服务。个人使用通常没问题，
  **商用前请自行确认微软的服务条款**，或改用 Azure Speech / ElevenLabs 等有明确商用授权的服务。
- **模型服务**：Gemini / Qwen / 豆包 / OpenAI 各自有服务条款与计费规则。本项目不代理也不转售这些额度。

## 7. 商标

「VideoNarrator AI」为项目名称，不授予商标许可。Apache-2.0 第 6 条保留商标权。
