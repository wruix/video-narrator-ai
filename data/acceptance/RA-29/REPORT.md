# RA-29 · Candidate Artifact Acceptance Audit（Run #7 四平台全绿后的候选交付验收）

- 审计日期：2026-10-27（日志时间 2026-10-26 UTC）
- 仓库/分支：`F:\视频解说` / `release-candidate/ra-15`
- 审计性质：**只读验收审计**。未修改应用代码、工作流、依赖、构建配置或哈希清单；未提交代码、未推送、未创建 Tag/Release、未合并。
- 最终状态：**`ACCEPTED_WITH_LIMITATIONS`**
- 说明：`data/` 目录被 `.gitignore`（第 23 行 `data/`）整体排除，仓库内 `data/` 已跟踪文件数为 0，历史 RA-25～RA-28 报告同样未入库。本报告沿用既有约定存于工作区，未 force-add（若需入库，需所有者明确决定是否调整 `.gitignore` 或改放 `docs/acceptance/`）。

## 1. 审计范围与时间

| 项 | 内容 |
| --- | --- |
| 审计对象 | GitHub Actions Run #7（日志归档 `logs_109175404041.zip`）四平台候选构建 + Candidate Summary |
| 审计时间 | 2026-10-27（本地） |
| 证据来源 | 用户提供的 4 份相同日志归档（`data/acceptance/RA-29/`）+ 工作区源码/配置静态核对 |
| 未使用 | 未执行下载的安装包、未运行任何二进制、未访问真实服务或凭据 |

## 2. 当前 Git 状态（只读固定）

| 项 | 值 |
| --- | --- |
| 当前分支 | `release-candidate/ra-15` |
| HEAD 完整 SHA | `6a71f72b2f4aef3d896cb4fcb82bc5be0b5c3547`（短 SHA `6a71f72` ✅ 符合预期） |
| `origin/release-candidate/ra-15`（本地 ref） | `6a71f72b2f4aef3d896cb4fcb82bc5be0b5c3547` ✅ 与 HEAD 一致 |
| `master` | `1fb78651e7c1d9e01e61f9e5bc00366153c8a10b` ✅ 与已知基线一致，未改动 |
| 工作区/暂存区 | 无已跟踪文件改动；仅 12 个已知 untracked 审计脚手架文件（`RA-18-audit/`、`scripts/_patch_modelname.py` 等，与本阶段无关） |
| RA-28 变更范围 | 2 文件：`.github/workflows/release-candidate-check.yml`（+8/−1）、`scripts/check_workflow_static.py`（+2/−2） |
| `config/ffmpeg-assets-lock.md` | `HEAD~6..HEAD` 内零改动（`git log --name-only` 无命中；`git diff HEAD~6` exit 0） |

> 备注：`git ls-remote` 在本次审计中遭遇网络超时/连接重置（`Recv failure`），未能实时查询远端 ref；本地 `origin/release-candidate/ra-15` ref 是 RA-28 推送成功后的快照，与本地 HEAD 一致。该网络限制不影响本次日志内证据。

## 3. Run #7 身份与 commit 绑定

| 项 | 证据 |
| --- | --- |
| 日志归档 | `logs_109175404041.zip`，126,247 B，SHA-256 `13D8E1028B3D3E90179581BF42736AE8158915880904D6EC4C5B52CB461E10E4`；4 份下载字节级完全一致 |
| 归档解压位置 | `data/acceptance/RA-29/ci-logs/extracted_run_109175404041_6a71f72/`（新建目录，未覆盖任何既有材料） |
| 运行标识 | 日志归档名 `logs_109175404041`；产物下载 URL 中运行号 `40283225648`（`https://github.com/wruix/video-narrator-ai/actions/runs/40283225648/...`）。两者为同一次运行的不同标识维度，均有日志佐证 |
| 分支绑定 | 各平台 `system.txt`：`Job defined at: wruix/video-narrator-ai/.github/workflows/release-candidate-check.yml@refs/heads/release-candidate/ra-15` |
| 完整 commit SHA | `6a71f72b2f4aef3d896cb4fcb82bc5be0b5c3547`；**4 个平台聚合日志各命中 15 次**；Candidate Summary 产物内容自述 `- **Commit**: 6a71f72b2f4aef3d896cb4fcb82bc5be0b5c3547` |
| 触发时间 | 作业启动 `2026-10-26T07:01:09Z`（4 平台 system.txt 一致）；Candidate Summary 生成时间 `2026-10-26 07:06 UTC` |

**绑定结论**：Run #7 = `6a71f72`（RA-28 提交），非其它提交或旧运行。`EVIDENCE_VERIFIED`。

## 4. 四平台 job 与关键步骤矩阵

所有平台聚合日志中**无任何真实 `##[error]`/`Process completed with exit code` 行**（步骤日志中出现的 `##[error]` 字样均为 GitHub Actions 回显的脚本源码文本，非运行时错误；已逐条比对确认）。

| 步骤（按工作流顺序） | Windows-x64 | macOS-Intel-x64 | macOS-AppleSilicon-arm64 | Linux-x64 |
| --- | --- | --- | --- | --- |
| checkout / setup-node / setup-python | ✅ | ✅ | ✅ | ✅ |
| FFmpeg 下载 + SHA-256 校验 | ✅ Expected=Actual=`60f4672…047ba` | ✅ | ✅ | ✅ |
| npm ci / pip / build:web / build:desktop | ✅ | ✅ | ✅ | ✅ |
| PyInstaller 独立后端 | ✅ | ✅ | ✅ | ✅ |
| Media self-check（打包前） | ✅ | ✅ | ✅ | ✅ |
| Preflight app-builder（只读） | ✅ | ✅ | ✅ | ✅ |
| **Package desktop app（electron-builder）** | ✅ | ✅ | ✅ | ✅ |
| Post-build 诊断（always） | ✅ | ✅ | ✅ | ✅ |
| **Record artifact info（第 19 步）** | ⚠️ 通过但哈希不可用 | ✅ 含 SHA-256 | ✅ 含 SHA-256 | ✅ 含 SHA-256 |
| **Verify bundled FFmpeg/server（第 20 步硬断言）** | ✅ `OK` | ✅ `OK` | ✅ `OK` | ✅ `OK` |
| Upload candidate artifact | ✅ | ✅ | ✅ | ✅ |
| 作业最终结论 | ✅ 成功 | ✅ 成功 | ✅ 成功 | ✅ 成功 |

### 4.1 Windows 第 20 步（RA-28 修复后）实证

```
Resources dir: D:\a\video-narrator-ai\video-narrator-ai/apps/desktop/release/win-unpacked/resources/server
-rwxr-xr-x 1 runneradmin 197121 105423872 Oct 26 07:01 ffmpeg.exe
-rwxr-xr-x 1 runneradmin 197121 105221120 Oct 26 07:01 ffprobe.exe
-rwxr-xr-x 1 runneradmin 197121  26315584 Oct 26 07:03 vns-server.exe
OK: server + ffmpeg/ffprobe resources are bundled under …/win-unpacked/resources/server
```

RA-28 的 `case "$runner_os"` 修复生效：目录定位成功，硬断言通过。

## 5. 候选产物与 SHA-256 证据表

### 5.1 GitHub Actions artifact（上传包）

| 平台 | artifact 名称 | Artifact ID | 大小（字节） | 上传状态 | 下载 URL（日志内） |
| --- | --- | --- | --- | --- | --- |
| Windows x64 | `candidate-Windows-x64` | 12632902399 | 385,789,490 | ✅ 成功 | `…/runs/40283225648/artifacts/12632902399` |
| macOS Intel x64 | `candidate-macOS-Intel-x64` | 12632738926 | 792,705,614 | ✅ 成功 | `…/artifacts/12632738926` |
| macOS ARM64 | `candidate-macOS-AppleSilicon-arm64` | 12632778517 | 745,368,362 | ✅ 成功 | `…/artifacts/12632778517` |
| Linux x64 | `candidate-Linux-x64` | 12633192159 | 627,582,450 | ✅ 成功 | `…/artifacts/12633192159` |
| 汇总 | `candidate-summary` | 12632819063 | 820 | ✅ 成功（zip 摘要 `30fbe2ca…d8b7b`） | `…/artifacts/12632819063` |

> artifact ZIP 本身的 SHA-256：仅 `candidate-summary` 在日志中打印了摘要；4 个平台候选 ZIP 的摘要未出现在日志中（GitHub UI 才显示），故 **NOT_PROVEN**。

### 5.2 包内安装包（日志第 19 步记录）

| 平台 | 文件 | 大小（字节） | SHA-256（来自 CI 第 19 步实际计算） |
| --- | --- | --- | --- |
| Windows | `VideoNarrator AI-1.0.0-x64.exe`（nsis+portable 同名，最终为 portable 覆盖） | 162,483,251 | ❌ **未记录**（见 §8 发现 F1） |
| Windows | `win-unpacked/VideoNarrator AI.exe` | 188,784,128 | ❌ 未记录 |
| Windows | `win-unpacked/resources/server/ffmpeg.exe` | 105,423,872 | ❌ 未记录 |
| Windows | `win-unpacked/resources/server/ffprobe.exe` | 105,221,120 | ❌ 未记录 |
| Windows | `win-unpacked/resources/server/vns-server.exe` | 26,315,584 | ❌ 未记录 |
| Windows | `win-unpacked/resources/elevate.exe` | 107,520 | ❌ 未记录 |
| macOS Intel | `VideoNarrator AI-1.0.0-x64.dmg` | ≈187M（`ls -lh`，精确字节未打印） | `f4766b1c33a0d2233131ec49f0de02f186fb77a38036d423950275b35eebfa8b` |
| macOS Intel | `VideoNarrator AI-1.0.0-x64.zip` | ≈181M（`ls -lh`） | `b1e9fa882dfb77862a2a21e76863784342c6215e67ba4433c807f28c1db054aa` |
| macOS ARM64 | `VideoNarrator AI-1.0.0-arm64.dmg` | ≈173M（`ls -lh`） | `69c8ffde49a01b0250076edf0ee38d24dd9ee4577201553f1049788355fc5425` |
| macOS ARM64 | `VideoNarrator AI-1.0.0-arm64.zip` | ≈168M（`ls -lh`） | `c83583094443371fa8a87a992eb1e3cf77a7d64bdb30d8603a79325d33057c54` |
| Linux | `VideoNarrator AI-1.0.0-amd64.deb` | 173,689,802 | `327f98781472bc9be39d4924c8c3bc9fbc69fd5e9262fbfeb85d3cc6485083e4` |
| Linux | `VideoNarrator AI-1.0.0-x86_64.AppImage` | 226,733,102 | `0b98331833821ea064ae7941d14f23d3d0b9d2848879e42a0f32a59559e246be` |

- 上述 SHA-256 均为 **CI 运行时计算并打印**（macOS/Linux 用 POSIX 路径，成功）；Windows 全部为占位标记（见 §8 F1）。
- macOS 精确字节数：CI 第 19 步在 macOS 上走了 `ls -lh` 回退分支（BSD `find` 无 `-printf`），仅有人类可读大小，**精确字节 NOT_PROVEN**。
- 未下载任何候选 artifact 到本地 → 安装包内容、包内文件清单、签名状态等**未做本地只读复验**。

## 6. `server` / FFmpeg / FFprobe 打包证据（第 20 步硬断言，四平台一致）

| 平台 | 资源目录（第 20 步实际输出） | vns-server | ffmpeg | ffprobe | 断言结果 |
| --- | --- | --- | --- | --- | --- |
| Windows | `…/release/win-unpacked/resources/server` | `vns-server.exe` 26,315,584 B | `ffmpeg.exe` 105,423,872 B | `ffprobe.exe` 105,221,120 B | ✅ `OK` |
| Linux | `…/release/linux-unpacked/resources/server` | `vns-server` 51,582,880 B | `ffmpeg` 91,342,624 B | `ffprobe` 91,141,792 B | ✅ `OK` |
| macOS Intel | `…/release/mac/VideoNarrator AI.app/Contents/Resources/server` | `vns-server` 25,080,192 B | `ffmpeg` 94,769,296 B | `ffprobe` 94,594,080 B | ✅ `OK` |
| macOS ARM64 | `…/release/mac-arm64/VideoNarrator AI.app/Contents/Resources/server` | `vns-server` 26,137,552 B | `ffmpeg` 66,332,880 B | `ffprobe` 66,158,064 B | ✅ `OK` |

- 该步骤在 RA-27 已从"空验证"升级为硬断言（目录缺失或 `vns-server*`/`ffmpeg*`/`ffprobe*` 任一缺失 → `exit 1`），本 run 四平台均输出 `OK`，属**真验证**。
- Linux `ffmpeg`/`ffprobe` 大小为硬链接计数（`2` links），与 Windows/macOS 各自独立文件形态一致，均非空壳。
- **边界**：这是"打包输出目录内资源存在"的实证，不等价于"最终 `.dmg`/`.zip`/`.AppImage`/`.deb` 内同样存在"（未解包核验），也不等价于"应用可运行"。

## 7. Candidate Summary 证据

| 项 | 证据 |
| --- | --- |
| 执行状态 | **实际执行成功**（非跳过、非失败）：日志含完整 job 步骤、`Generate summary`、`Upload summary`、`Post job cleanup` |
| 门禁 | `needs: candidate-build`；该作业运行本身即证明 4 个矩阵作业全部 success（否则不会触发） |
| 生成内容 | `candidate-summary.md`，含 `- **Commit**: 6a71f72b2f4aef3d896cb4fcb82bc5be0b5c3547`、`- **Date**: 2026-10-26 07:06 UTC`、制品说明与人工验收步骤 |
| 上传 | `candidate-summary.zip`，820 B，Artifact ID 12632819063，SHA-256 `30fbe2cab8ac287c3dc78eae280ad3547d33c34b83a9f5791b486d32fd6d8b7b` |
| 局限 | 汇总内容为模板化文本，未逐平台列举上传结果/大小/哈希（不影响其作为门禁证据） |

## 8. 失败、跳过、未执行与 NOT_PROVEN 清单

### 8.1 本次运行内的失败/跳过
- 失败作业：**无**（4 平台 + Summary 全部成功）。
- 跳过步骤：**无**（各平台全部步骤均执行）。

### 8.2 证据缺项（NOT_PROVEN）
1. **Windows 包内制品 SHA-256**（6 个文件）未记录，日志为 `(hash unavailable for: D:avideo-…)`。
2. macOS 包内制品的**精确字节数**（仅 `ls -lh` 人类可读值）。
3. 4 个平台候选 artifact ZIP 的摘要（日志未打印）。
4. **候选产物实际内容**：未下载 artifact，未做包内文件清单/SHA 复验，未解包 `.dmg`/`.zip`/`.app`/`.AppImage`/`.deb`。
5. **运行验收**：未安装、未启动、未验证后端健康检查与视频探测（按审计规则禁止）。
6. Windows 产物命名：nsis 与 portable 同 artifactName（`-x64.exe`），日志显示两者先后写入同一路径；最终上传的是 portable 覆盖后的文件——**该覆盖语义未在文档/日志中显式声明**，属可复核风险点（见 F3）。

### 8.3 新发现（仅记录，未修改任何代码）

**F1（Windows 第 19 步哈希不可用的真实根因，优先级：中）**
- 现象：6 个文件全部 `(hash unavailable)`，同一步骤在 macOS/Linux 均正常。
- 根因（证据链）：`find` 输出的是 `GITHUB_WORKSPACE` 反斜杠路径（如 `D:\a\video-narrator-ai\...`）；脚本用 `while read f`（**未加 `-r`**），POSIX `read` 会把 `\a`、`\v` 等当转义序列吞掉，`$f` 变成 `D:avideo-narrator-aivideo...`，随后 `sha256sum < "$f"` 打开失败 → 走占位分支。Run #6 日志中 `line 18: D:avideo-…: No such file or directory` 直接印证反斜杠被吞。
- 说明：RA-27 的 stdin 重定向修复方向正确（不再 127/`shasum`），但未解决 `read` 丢字符问题，故 Windows 仍拿不到哈希。
- 建议修复（下一轮，需所有者批准）：`while IFS= read -r f`；对 Windows 路径追加 `cygpath -u` 归一化守卫；并在哈希失败时输出实际错误而非静默占位。

**F2（macOS 精确大小不可得，优先级：低）**
- BSD `find` 不支持 `-printf`，回退 `ls -lh` 丢失字节精度；建议回退分支改用 `stat -f%z`（mac）/`stat -c%s`（linux）或 `wc -c < "$f"`。

**F3（Windows 双 target 同名覆盖，优先级：低）**
- `win.target` 同时声明 `nsis` 与 `portable`，且 `artifactName` 相同 → 后者覆盖前者，上传物实为 portable 单文件版而非安装器。若期望同时交付两者，应区分 artifactName（例如加 `-portable` 后缀）。**需所有者确认交付意图**。

**F4（签名状态，优先级：中，属预期内待办）**
- macOS：`0 valid identities found`，签名/公证均跳过；Windows：`no signing info identified, signing is skipped`。产物未签名 → macOS Gatekeeper 会拦截、Windows SmartScreen 会告警。发布前需明确签名方案（本阶段不涉及）。

**F5（图标，优先级：低）**
- 4 平台均 `default Electron icon is used  reason=application icon is not set`（`build/icon.*` 未提供有效图标），品牌与安装体验缺失。

**F6（GitHub artifact 大小 385–792 MB，优先级：低）**
- 主要体积来自 ffmpeg+ffprobe（每平台约 160–200 MB 合计）+ PyInstaller 后端；与"独立分发 FFmpeg"的设计一致，但需注意 artifact 保留期 30 天与下载成本。

## 9. 既有报告、日志与用户文件保护情况

- 未删除/覆盖/移动/重命名任何既有材料：`RA-25/RA-26/RA-27/RA-28` 全部原样保留（`RA-26` 两份 ZIP、`RA-27` 一份 ZIP 及解压目录、各报告 mtime 未变）。
- Run #7 归档解压到**新目录** `data/acceptance/RA-29/ci-logs/extracted_run_109175404041_6a71f72/`。
- 4 份重复下载的 ZIP 原样保留在 `data/acceptance/RA-29/`。
- 未读取/输出 `data/master.key`、`.env`、令牌、Cookie 或 Authorization header（本阶段所有操作仅涉及日志、源码与 Git 元数据）。

## 10. 结论与下一步

### 结论
四平台 CI **真实全绿**（日志独立核验，非采信口头报告），commit 绑定 `6a71f72`，四平台候选 artifact 全部上传成功，`resources/server/{vns-server,ffmpeg,ffprobe}` 在打包输出目录经**硬断言**验证存在，Candidate Summary 实际执行成功，FFmpeg 哈希清单未变更且四平台校验通过。存在已披露的证据缺口（Windows 哈希未记录、产物未下载复验、未签名、Windows 双 target 覆盖），故判定：

**`ACCEPTED_WITH_LIMITATIONS`**

### 仍需人工提供的材料
1. 4 个平台候选 artifact ZIP（若需本地包内复验）：`candidate-Windows-x64`、`candidate-macOS-Intel-x64`、`candidate-macOS-AppleSilicon-arm64`、`candidate-Linux-x64`（Actions → Run #7 → Artifacts）。
2. macOS 实机（Intel/ARM）与 Linux 实机的安装启动验收记录（本审计禁止运行二进制）。
3. 所有者对 F3（nsis/portable 交付意图）与 F4（签名方案）的决策。

### 下一阶段建议（按优先级）
1. **RA-30（建议）**：修复 F1（`read -r` + 路径归一化 + 哈希失败显式报错），并同步 checker 断言；可选同时修 F2（精确大小）。属工作流工具链修复，不动应用代码。
2. **RA-31（建议）**：产物包内复验脚本/流程（对下载的 artifact 做只读解包 + 清单 + 内层 SHA-256 与 §5.2 对比），补齐 §8.2 第 4 项。
3. **RA-32（发布前必须）**：签名/公证方案 + 图标 + Windows 交付形态决策，然后才谈 Release。

### 停止点
本轮到此停止：**未提交代码、未推送、未创建 Tag/Release、未合并**。等待所有者决定是否进入 RA-30 及是否提供产物 ZIP 用于本地复验。
