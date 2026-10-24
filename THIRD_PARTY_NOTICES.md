# Third-Party Notices

本项目在**运行时**依赖以下第三方组件，但**不在仓库中分发**它们。
安装包若附带任何第三方二进制文件，必须同时附带其许可文本。

---

## 运行时依赖（由用户自行安装）

### FFmpeg / FFprobe（随包分发）

- 项目主页：https://ffmpeg.org/
- 本地验证的二进制版本：n8.1.3-20-gc8de997cb1-20261021（Windows x64，static build，来自 gyan.dev 构建）
- 构建配置（来自 `-buildconf`）：`--enable-gpl` 已启用，arch=x86_64，target-os=mingw32，交叉编译器 x86_64-w64-mingw32-gcc
- 启用的 GPL 组件示例：`--enable-libx264 --enable-libx265 --enable-libxvid --enable-libxavs2 --enable-libsvtav1 --enable-librav1e --enable-libaom --enable-libdav1d --enable-libvmaf --enable-libzvbi --enable-libsrt --enable-libvpl --enable-libopenh264 --enable-ffnvcodec --enable-cuda-llvm` 等
- 启用的 LGPL 组件示例：`--enable-libmp3lame --enable-libopus --enable-libtheora --enable-libvorbis --enable-libvpx --enable-libwebp --enable-libass --enable-libfreetype --enable-libfontconfig` 等
- **许可证判定**：由于构建时启用了 `--enable-gpl`，并链接了 x264、libx265 等 GPL 授权的第三方库，该 FFmpeg 构建整体适用 **GPL-2.0+**（而非单纯 LGPL）。随包分发时必须：
  1. 附带 `COPYING.GPLv3`（或对应 GPL 版本文本）；
  2. 提供源代码获取方式（FFmpeg 源码及所使用第三方库的源码）；
  3. 遵守 GPL 对整体发行物的传染性要求；
- 本项目的使用方式：以子进程方式调用 `ffmpeg` / `ffprobe`，**不链接**其代码，但随包分发二进制本身仍需遵循上述 GPL 义务。
- 未来如果切换为 LGPL-only 构建（禁用 `--enable-gpl` 及所有 GPL 库），则可改为附带 `COPYING.LGPLv3` 并允许用户替换该库。

### 各平台资产来源与锁定状态（RA-14 核实）

| 平台 | 来源 | 版本 | SHA-256 | 状态 |
| --- | --- | --- | --- | --- |
| Windows x64 | [Gyan.dev](https://www.gyan.dev/ffmpeg/builds/) | 9.0.2 | `60f46726...fa2047ba` | ✅ 已锁定 |
| macOS x64 | [Martin Riedl](https://ffmpeg.martin-riedl.de/) | 9.0.2 | `7c6b4125...e47cacd4` | ✅ 已锁定（来源确认，本地无法下载验证） |
| macOS arm64 | [Martin Riedl](https://ffmpeg.martin-riedl.de/) | 9.0.2 | `c8ed4c4e...4492d924` | ✅ 已锁定（来源确认，本地无法下载验证） |
| Linux x64 | [Martin Riedl](https://ffmpeg.martin-riedl.de/) | 9.0.2 | `fa8ecf4a...5aab1909d7f` | ✅ 已锁定（来源确认，本地无法下载验证） |

完整 SHA-256 及下载 URL 见 `config/ffmpeg-assets-lock.md`。

**各平台许可证义务**：

| 平台 | 来源 | 许可证判定 | 备注 |
| --- | --- | --- | --- |
| Windows x64 | Gyan.dev 9.0.2 | GPL-3.0（已确认） | `-buildconf` 显示 `--enable-gpl`，含 libx264/libx265 等 GPL 库 |
| macOS x64 | Martin Riedl 9.0.2 | GPL（待 `-buildconf` 确认） | 官网列出 x264、x265、aom、dav1d 等外部库；已签名和公证 |
| macOS arm64 | Martin Riedl 9.0.2 | GPL（待 `-buildconf` 确认） | 同上，Apple Silicon 原生构建 |
| Linux x64 | Martin Riedl 9.0.2 | GPL（待 `-buildconf` 确认） | 同上 |

> **注意**：Martin Riedl 构建在官网声明含 x264、x265 等 GPL 编码库，大概率适用 GPL。
> 各平台实际许可证需下载后执行 `-buildconf` 确认，目前仅有 Windows 已完成该审核。

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
