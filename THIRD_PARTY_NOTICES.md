# Third-Party Notices

本项目在**运行时**依赖以下第三方组件，但**不在仓库中分发**它们。
安装包若附带任何第三方二进制文件，必须同时附带其许可文本。

---

## 运行时依赖（由用户自行安装）

### FFmpeg / FFprobe

- 项目主页：https://ffmpeg.org/
- 许可：LGPL-2.1+ 或 GPL-2+，取决于构建配置
- 本项目的使用方式：以子进程方式调用**用户自行安装**的 `ffmpeg` / `ffprobe`，不链接其代码

**如果你的发行版附带 FFmpeg 二进制**，请根据实际使用的构建：

- LGPL 构建：需附带 `COPYING.LGPLv3`，并允许用户替换该库；
- GPL 构建：需附带 `COPYING.GPLv3`，且整体发行物需符合 GPL 要求；
- 启用 `--enable-gpl` 的构建通常涉及 x264、libx265 等 GPL 组件。

常用静态构建来源：

| 来源 | 许可 | 说明 |
| --- | --- | --- |
| [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) | GPL / LGPL | Windows / Linux 静态构建 |
| [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/) | GPL / LGPL | Windows 静态构建 |

### Python

- 许可：PSF License 2.0（宽松，与 Apache-2.0 兼容）
- 项目主页：https://www.python.org/

### Node.js / Electron

- 许可：MIT
- 项目主页：https://nodejs.org/ , https://www.electronjs.org/

---

## Python 依赖

| 组件 | 许可 |
| --- | --- |
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| SQLAlchemy | MIT |
| Pydantic | MIT |
| httpx | BSD-3-Clause |
| cryptography | Apache-2.0 / BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| edge-tts | LGPL-3.0 |

---

## 前端依赖

| 组件 | 许可 |
| --- | --- |
| React / React-DOM | MIT |
| Vite | MIT |
| TypeScript | Apache-2.0 |
| i18next / react-i18next | MIT |
| Zustand | MIT |

---

## 模型服务（外部 API，非随包分发）

| 服务 | 条款 |
| --- | --- |
| Google Gemini | Google APIs 服务条款 |
| 通义千问 / 阿里云百炼 | 阿里云服务条款 |
| 豆包 / 火山方舟 | 火山引擎服务条款 |
| OpenAI | OpenAI 服务条款 |
| 硅基流动 | 硅基流动服务条款 |
| Azure Speech | Azure 服务条款 |
| ElevenLabs | ElevenLabs 服务条款 |
| Microsoft Edge TTS | 微软 Edge 朗读服务条款（商用前请确认） |

> 本项目不代理、不转售、不打包任何模型额度。所有模型调用由用户自己的账号发起。

---

## 生成物说明

本仓库**不包含**任何第三方二进制文件。以下内容需要在构建时自行获取并遵守其许可：

- 桌面端安装包中的 `resources/server/vns-server`（由 PyInstaller 打包的本地后端）
- 任何随包分发的 FFmpeg 静态构建
- 应用图标资源（请使用自有或明确授权的素材）

**维护者发布发行版时，请在本文件补充实际随包分发的组件清单。**
