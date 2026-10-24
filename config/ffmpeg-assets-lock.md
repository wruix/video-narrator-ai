# FFmpeg 资产锁定清单

本文件记录每个平台 FFmpeg/FFprobe 的固定版本、下载 URL、SHA-256 校验和及许可证。
CI 构建时据此验证下载完整性。任何未填入实际哈希的条目意味着对应平台 CI 构建将失败。

> 本文件必须被 Git 追踪（`config/ffmpeg-assets-lock.md`）。
> 本地 FFmpeg/FFprobe 生成二进制（`services/api/ffmpeg-bin/`）不入库，由 CI 按本清单下载。

---

## 已锁定资产

### Windows x64 — Gyan.dev FFmpeg 9.0.2

| 字段 | 值 |
|------|-----|
| 来源 | https://www.gyan.dev/ffmpeg/builds/ |
| 版本 | 9.0.2 |
| 下载 URL | https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip |
| 格式 | ZIP (109 MB) |
| SHA-256 | `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba` |
| 校验来源 | https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256（官方发布页） |
| 架构 | x86_64 (Windows, target-os=mingw32, UCRT64) |
| 许可证 | GPL-3.0（`--enable-gpl` 已启用，含 libx264/libx265 等 GPL 库） |
| 验证时间 | RA-13, 2026-10-23 |
| CI 验证 | RA-15 候选构建工作流（`release-candidate-check.yml`）：下载 SHA-256 校验 + `-buildconf` + 媒体自检（待 CI 执行） |
| 本地验证 | ✅ `-version`、`-buildconf`、ffprobe 探测（h264 320x240）、MP4 生成（72,900B）均通过 |
| 状态 | ✅ SHA-256 已锁定；本地执行验证通过 |

### macOS x64 — Martin Riedl FFmpeg 9.0.2

| 字段 | 值 |
|------|-----|
| 来源 | https://ffmpeg.martin-riedl.de/ |
| 版本 | 9.0.2（release build，创建时间 2026-09-20） |
| FFmpeg 下载 URL | https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/ffmpeg.zip |
| FFprobe 下载 URL | https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/ffprobe.zip |
| 格式 | ZIP |
| FFmpeg SHA-256 | `7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4` |
| FFprobe SHA-256 | `2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd` |
| 校验来源 | https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/ffmpeg.zip.sha256 |
| 架构 | x86_64 (macOS Intel) |
| 签名 | macOS 二进制已签名（zip 和 installer）并公证（installer） |
| 许可证 | GPL（需下载后 `-buildconf` 确认） |
| 验证时间 | RA-14, 2026-10-23 |
| CI 验证 | RA-15 候选构建工作流：`macos-15-intel` Runner（标签可用性待确认） |
| 状态 | ✅ SHA-256 已锁定（来源已确认，本地无法实际下载验证；CI 下载校验待执行） |

### macOS arm64 — Martin Riedl FFmpeg 9.0.2

| 字段 | 值 |
|------|-----|
| 来源 | https://ffmpeg.martin-riedl.de/ |
| 版本 | 9.0.2（release build，创建时间 2026-09-20） |
| FFmpeg 下载 URL | https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffmpeg.zip |
| FFprobe 下载 URL | https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffprobe.zip |
| 格式 | ZIP |
| FFmpeg SHA-256 | `c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924` |
| FFprobe SHA-256 | `fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6` |
| 校验来源 | https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffmpeg.zip.sha256 |
| 架构 | arm64 (Apple Silicon，原生) |
| 签名 | macOS 二进制已签名（zip 和 installer）并公证（installer） |
| 许可证 | GPL（需下载后 `-buildconf` 确认） |
| 验证时间 | RA-14, 2026-10-23 |
| CI 验证 | RA-15 候选构建工作流：`macos-15` Runner（macOS Apple Silicon arm64） |
| 状态 | ✅ SHA-256 已锁定（来源已确认，本地无法实际下载验证；CI 下载校验待执行） |

### Linux x64 — Martin Riedl FFmpeg 9.0.2

| 字段 | 值 |
|------|-----|
| 来源 | https://ffmpeg.martin-riedl.de/ |
| 版本 | 9.0.2（release build，创建时间 2026-09-20） |
| FFmpeg 下载 URL | https://ffmpeg.martin-riedl.de/download/linux/amd64/1789931100_9.0.2/ffmpeg.zip |
| FFprobe 下载 URL | https://ffmpeg.martin-riedl.de/download/linux/amd64/1789931100_9.0.2/ffprobe.zip |
| 格式 | ZIP |
| FFmpeg SHA-256 | `fa8ecf4abbd290d98f7d188b8649cc6b391ae209a98452be955a15aab1909d7f` |
| FFprobe SHA-256 | `3f428c49070be3d24ec338602b76d412e401ffcb8a5641ef0e729181a232fc32` |
| 校验来源 | https://ffmpeg.martin-riedl.de/download/linux/amd64/1789931100_9.0.2/ffmpeg.zip.sha256 |
| 架构 | amd64 (Linux x64) |
| 许可证 | GPL（需下载后 `-buildconf` 确认） |
| 验证时间 | RA-14, 2026-10-23 |
| CI 验证 | RA-15 候选构建工作流：`ubuntu-latest` Runner（Linux x64） |
| 状态 | ✅ SHA-256 已锁定（来源已确认，本地无法实际下载验证；CI 下载校验待执行） |

---

## 替代方案（已弃用）

- **evermeet.cx**：不提供固定版本 SHA-256（仅滚动 latest），不适用。
- **johnvansickle.com**：只提供 MD5，且版本 7.0.2 与 9.0.2 不一致，不适用。
- **BtbN/FFmpeg-Builds**：git master 滚动更新，非固定版本号，不适合作为正式发布制品来源。

---

## 许可证摘要

| 平台 | 来源 | 许可证 | 备注 |
|------|------|--------|------|
| Windows x64 | Gyan.dev 9.0.2 | GPL-3.0 | `--enable-gpl` 已启用，含 libx264/libx265 等 GPL 库，需附带 GPL 文本和源码获取方式 |
| macOS x64 | Martin Riedl 9.0.2 | GPL（待 `-buildconf` 确认） | 已签名和公证；外部库含 x264、x265、aom、dav1d 等（见官网 codec 列表） |
| macOS arm64 | Martin Riedl 9.0.2 | GPL（待 `-buildconf` 确认） | 同 macOS x64，架构为 Apple Silicon 原生 |
| Linux x64 | Martin Riedl 9.0.2 | GPL（待 `-buildconf` 确认） | 外部库同 Martin Riedl 构建脚本声明 |
