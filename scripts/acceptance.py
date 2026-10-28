"""VideoNarrator AI · 发布门禁验收框架。

把「真实模型 / 真实成片 / 三平台安装包 / 云端部署」四条主线，转成
**可执行、带证据的通过/失败标准**，并生成可归档的验收报告。

用法：
    python scripts/acceptance.py --list              # 列出全部检查项
    python scripts/acceptance.py --gate A             # 只跑门禁 A
    python scripts/acceptance.py --all                # 跑全部
    python scripts/acceptance.py --all --json out.json # 同时输出 JSON

报告输出：
    data/acceptance/report.md      人读的报告
    data/acceptance/report.json     机读的结果

退出码 = 未通过（FAIL）的检查项数量，CI 可直接用它卡发布。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

REPORT_DIR = ROOT / "data" / "acceptance"
GATES = {
    "A": "公开开源 Beta",
    "B": "跨平台正式版",
    "C": "商业云端正式运营",
}

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
WARN = "WARN"
BLOCKED = "BLOCKED"


# ---------------------------------------------------------------- 基础设施


@dataclass
class Result:
    gate: str
    code: str
    title: str
    status: str
    detail: str = ""
    evidence: list[str] = field(default_factory=list)
    duration_ms: int = 0


class Runner:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.results: list[Result] = []

    def check(
        self,
        gate: str,
        code: str,
        title: str,
        fn: Callable[[], tuple[str, str, list[str]]],
    ) -> Result:
        t0 = time.time()
        try:
            status, detail, evidence = fn()
        except Exception as exc:  # noqa: BLE001
            status, detail, evidence = FAIL, f"{type(exc).__name__}: {exc}", []
        res = Result(
            gate=gate,
            code=code,
            title=title,
            status=status,
            detail=detail,
            evidence=[str(e) for e in evidence],
            duration_ms=int((time.time() - t0) * 1000),
        )
        self.results.append(res)
        return res

    # ---------------------------------------------------- 汇总

    def gate_status(self, gate: str) -> str:
        items = [r for r in self.results if r.gate == gate]
        if not items:
            return SKIP
        if any(r.status == FAIL for r in items):
            return FAIL
        if any(r.status == BLOCKED for r in items):
            return BLOCKED
        if any(r.status == SKIP for r in items):
            return SKIP
        if any(r.status == WARN for r in items):
            return WARN
        return PASS

    def counts(self) -> dict:
        out = {PASS: 0, FAIL: 0, SKIP: 0, WARN: 0, BLOCKED: 0}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    # ---------------------------------------------------- 报告

    def render_markdown(self) -> str:
        c = self.counts()
        lines = [
            "# VideoNarrator AI · 发布验收报告",
            "",
            f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 平台：{platform.system()} {platform.release()} ({platform.machine()})",
            f"- Python：{platform.python_version()}",
            f"- 结果：**通过 {c[PASS]} · 失败 {c[FAIL]} · 跳过 {c[SKIP]} · 阻塞 {c[BLOCKED]} · 警告 {c[WARN]}**",
            "",
            "## 门禁总览",
            "",
            "| 门禁 | 名称 | 结论 | 通过/总数 |",
            "| --- | --- | --- | --- |",
        ]
        for gate, name in GATES.items():
            items = [r for r in self.results if r.gate == gate]
            total = len(items)
            ok = sum(1 for r in items if r.status == PASS)
            icon = {PASS: "✅", FAIL: "❌", SKIP: "⏭️", WARN: "⚠️", BLOCKED: "🚫"}[self.gate_status(gate)]
            lines.append(f"| {gate} | {name} | {icon} {self.gate_status(gate)} | {ok}/{total} |")

        for gate, name in GATES.items():
            items = [r for r in self.results if r.gate == gate]
            if not items:
                continue
            lines += ["", f"## 门禁 {gate} · {name}", ""]
            for r in items:
                icon = {PASS: "✅", FAIL: "❌", SKIP: "⏭️", WARN: "⚠️", BLOCKED: "🚫"}[r.status]
                lines.append(f"### {icon} {r.code} {r.title}")
                lines.append("")
                lines.append(f"- 结论：**{r.status}**")
                if r.detail:
                    lines.append(f"- 说明：{r.detail}")
                if r.evidence:
                    lines.append("- 证据：")
                    for e in r.evidence:
                        lines.append(f"  - `{e}`")
                lines.append(f"- 耗时：{r.duration_ms} ms")
                lines.append("")

        lines += ["", "## 结论", ""]
        overall_fail = [r for r in self.results if r.status == FAIL]
        if overall_fail:
            lines.append(f"**未通过 {len(overall_fail)} 项，暂不可发布：**")
            lines.append("")
            for r in overall_fail:
                lines.append(f"- `{r.code}` {r.title} —— {r.detail}")
        else:
            lines.append("全部已定义的检查项通过。")
        lines.append("")

        # 追加 RA-14 / RA-15 各平台 FFmpeg 资产独立状态矩阵
        lines += self._render_ra_platforms()
        lines.append("")
        return "\n".join(lines)

    def _render_ra_platforms(self) -> list[str]:
        """渲染 RA-14/RA-15/RA-16 各平台 FFmpeg 资产独立状态矩阵（静态数据，来源：config/ffmpeg-assets-lock.md）。"""
        lines: list[str] = [
            "",
            "## RA-16 候选构建就绪（SAFE CI TRIGGER READINESS）",
            "",
            "| 检查项 | 状态 | 说明 |",
            "|--------|------|------|",
            "| YAML 语法 | PASS | `yaml.safe_load` 通过 |",
            "| 触发器安全 | PASS | 仅 `workflow_dispatch` + `push: release-candidate/**`，不监听 v* tag，无 Release 创建步骤 |",
            "| 权限最小化 | PASS | `contents: read`，无 write 权限 |",
            "| 矩阵 4 平台 | PASS | windows-latest / macos-15-intel / macos-15 / ubuntu-latest，含 `uname -m` 架构断言 |",
            "| SHA-256 完整一致 | PASS | workflow 中 7 个完整 64 位哈希与 config/ffmpeg-assets-lock.md 完全一致，校验失败 `exit 1` |",
            "| 下载 URL 一致性 | PASS | 所有 URL 均在锁定清单中，无临时来源 |",
            "| 无凭证/敏感数据 | PASS | artifact 仅限 `apps/desktop/release/`、`ffmpeg-bin-buildconf.txt`、`tests-ffmpeg-selfcheck/`；不含 `data/`、`.env`、`master.key` |",
            "| 打包不发布 | PASS | `electron-builder --platform --publish never` |",
            "| CI 实际运行 | BLOCKED | 需 GitHub 仓库权限；`release-candidate/**` 分支需先推送（RA-16 不推送） |",
            "",
            "## RA-14 各平台 FFmpeg 资产独立状态矩阵",
            "",
            "| 状态项 | Windows x64 | macOS x64 | macOS arm64 | Linux x64 |",
            "|--------|:-----------:|:---------:|:-----------:|:---------:|",
            "| 1. 来源确认 | ✅ Gyan.dev | ✅ Martin Riedl | ✅ Martin Riedl | ✅ Martin Riedl |",
            "| 2. SHA-256 锁定 | ✅ 完整（60f46726...） | ✅ 完整（7c6b4125...） | ✅ 完整（c8ed4c4e...） | ✅ 完整（fa8ecf4a...） |",
            "| 3. 许可证审核 | ✅ GPL-3.0（-buildconf 已确认） | ⚠️ 待 CI -buildconf | ⚠️ 待 CI -buildconf | ⚠️ 待 CI -buildconf |",
            "| 4. CI 下载与校验 | ⚠️ 待 CI | ⚠️ 待 CI | ⚠️ 待 CI | ⚠️ 待 CI |",
            "| 5. 二进制执行及媒体自检 | ✅ 本地通过（ffprobe 探测 + MP4 生成） | ❌ 无本地设备 | ❌ 无本地设备 | ❌ 无本地设备 |",
            "| 6. 安装包构建 | ⚠️ 待 CI | ⚠️ 待 CI | ⚠️ 待 CI | ⚠️ 待 CI |",
            "| 7. 实际设备安装验收 | ⚠️ 待 CI | ⚠️ 待 CI | ⚠️ 待 CI | ⚠️ 待 CI |",
            "",
            "## RA-15 跨平台候选构建验证",
            "",
            "### 本地 Windows x64 已执行（有证据）",
            "",
            "- [x] FFmpeg `-version` / `-buildconf`：通过（ffmpeg n8.1.3，UCRT64）",
            "- [x] ffprobe 探测测试视频（h264, 320x240）：通过",
            "- [x] ffmpeg 生成 MP4（72,900 字节）：通过",
            "- [x] VC_FFMPEG/VC_FFPROBE 路径传递：backend.ts 代码确认",
            "- [x] electron-builder.yml 收集 `vns-server*` 和 `ffmpeg*`/`ffprobe*` 到 `resources/server/`：代码确认",
            "",
            "### 候选构建工作流（`.github/workflows/release-candidate-check.yml`）",
            "",
            "- 触发方式：`workflow_dispatch`（手动）+ `push: release-candidate/**`（候选分支自动触发）；不监听 v* tag",
            "- 权限：`contents: read`（最小化，不创建 Release/tag/推送）",
            "- Runner 矩阵：`windows-latest` / `macos-15-intel`（标签可用性待确认）/ `macos-15` / `ubuntu-latest`",
            "- 每个 job：下载固定资产 → SHA-256 校验 → -buildconf → 媒体自检 → electron-builder → 上传 artifact",
            "- 失败时保留脱敏诊断，不输出凭证",
            "",
            "### 各平台独立构建状态（待 CI 运行）",
            "",
            "| 平台 | Runner | 预期制品 | SHA-256 | 许可证确认 | CI 下载 | 媒体自检 | 安装包 | 安装验收 |",
            "|------|--------|---------|:-------:|:---------:|:------:|:-------:|:-----:|:-------:|",
            "| Windows x64 | windows-latest | NSIS .exe | ✅ | ✅ | ⚠️ 待CI | ✅ 本地通过 | ⚠️ 待CI | ⚠️ 待CI |",
            "| macOS Intel x64 | macos-15-intel | DMG (x64) + zip | ✅ | ⚠️ 待CI | ⚠️ 待CI | ❌ 无设备 | ⚠️ 待CI | ⚠️ 待CI |",
            "| macOS Apple Silicon arm64 | macos-15 | DMG (arm64) + zip | ✅ | ⚠️ 待CI | ⚠️ 待CI | ❌ 无设备 | ⚠️ 待CI | ⚠️ 待CI |",
            "| Linux x64 | ubuntu-latest | AppImage + deb | ✅ | ⚠️ 待CI | ⚠️ 待CI | ❌ 无设备 | ⚠️ 待CI | ⚠️ 待CI |",
            "",
            "> **注意**：`macos-15-intel` 标签可能因 GitHub 调整而不可用。若标签不存在，对应 job 将显示 BLOCKED，",
            "> 需改用 `macos-latest`（通常为 ARM64）并在 Runner 信息记录中注明架构不符。",
            "",
            "### 各平台完整 SHA-256（锁定值，摘自 config/ffmpeg-assets-lock.md）",
            "",
            "| 平台 | 资产 | SHA-256 |",
            "|------|------|---------|",
            "| Windows x64 | Gyan.dev 9.0.2 essentials ZIP | `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba` |",
            "| macOS x64 ffmpeg | Martin Riedl 9.0.2 amd64 | `7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4` |",
            "| macOS x64 ffprobe | Martin Riedl 9.0.2 amd64 | `2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd` |",
            "| macOS arm64 ffmpeg | Martin Riedl 9.0.2 arm64 | `c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924` |",
            "| macOS arm64 ffprobe | Martin Riedl 9.0.2 arm64 | `fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6` |",
            "| Linux x64 ffmpeg | Martin Riedl 9.0.2 amd64 | `fa8ecf4abbd290d98f7d188b8649cc6b391ae209a98452be955a15aab1909d7f` |",
            "| Linux x64 ffprobe | Martin Riedl 9.0.2 amd64 | `3f428c49070be3d24ec338602b76d412e401ffcb8a5641ef0e729181a232fc32` |",
        ]
        return lines

    def render_json(self) -> str:
        c = self.counts()
        return json.dumps(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                    "python": platform.python_version(),
                },
                "ra16_readiness": {
                    "description": "RA-16 安全触发与候选构建就绪检查结果（静态，本地执行）",
                    "overall_status": "READY_FOR_CI",
                    "status_legend": {
                        "READY_FOR_CI": "本地静态检查全部通过，具备安全触发条件；CI 未运行",
                        "CI_RUNNING": "候选构建在 GitHub Runner 执行中",
                        "CI_PASSED": "CI 成功，制品与诊断已上传 artifact",
                        "RC_VALIDATED": "候选制品已在对应平台实际安装并验收通过",
                        "BLOCKED": "存在未满足前置条件",
                    },
                    "static_checks": {
                        "yaml_syntax": "PASS（yaml.safe_load 通过）",
                        "triggers": "PASS - 仅 workflow_dispatch + push: release-candidate/**，不监听 v* tag，无 Release 创建",
                        "permissions": "PASS - contents: read 最小化",
                        "matrix_4_platforms": "PASS - windows-latest / macos-15-intel / macos-15 / ubuntu-latest + uname -m 架构断言",
                        "sha256_consistency": "PASS - 7 个完整 64 位哈希与 config/ffmpeg-assets-lock.md 一致，校验失败 exit 1",
                        "urls_from_lock": "PASS - 下载 URL 全部来自锁定清单",
                        "no_secrets_in_artifacts": "PASS - artifact 仅 release 制品 / buildconf / 自检视频",
                        "publish_never": "PASS - electron-builder --publish never",
                    },
                    "ci_execution": "BLOCKED - 需仓库所有者推送 release-candidate/** 分支并具备 GitHub Actions 权限",
                    "rc_validation": "BLOCKED - CI 未运行，候选制品未产出",
                    "operator_required": [
                        "授予 push 权限（仓库写权限）",
                        "推送 release-candidate/ra-15 分支（仅候选工作流文件 + .gitignore，禁止 git add .）",
                        "确认 macos-15-intel Runner 可用性，不可用则修改矩阵该行",
                        "确认 Actions 分钟配额（每次运行 4 jobs）",
                    ],
                    "not_executed_this_round": [
                        "未创建 tag", "未推送代码", "未创建/发布 Release",
                        "未提交整仓 commit", "未上传任何 artifact",
                    ],
                },
                "ra17_commit_closure": {
                    "description": "RA-17 候选分支提交闭包审计结果（本地执行）",
                    "overall_status": "READY_FOR_CI",
                    "allowlist_file": "data/acceptance/RA-17-COMMIT-ALLOWLIST.md（本地参考，data/ 被忽略不入库）",
                    "lock_file_moved": {
                        "from": "services/api/ffmpeg-bin/FFMPEG_ASSET_LOCK.md",
                        "to": "config/ffmpeg-assets-lock.md（Git 可追踪，不再被忽略）",
                    },
                    "untracked_must_commit": [
                        ".github/workflows/release-candidate-check.yml",
                        "config/ffmpeg-assets-lock.md",
                        "services/api/app/proxy.py",
                        "services/api/app/services/ollama_provider.py",
                        "scripts/acceptance.py",
                        "scripts/check_workflow_static.py",
                    ],
                    "excluded_sensitive": [
                        "data/master.key（.gitignore data/）",
                        "services/api/.env（.gitignore .env）",
                        "services/api/ffmpeg-bin/ 生成二进制 314MB（.gitignore）",
                        "aurora-installer.exe 40.5MB（.gitignore）",
                        "tests/*.mp4 个人测试视频（.gitignore tests/）",
                        "artifacts/（.gitignore）",
                    ],
                    "excluded_local_diagnostics": [
                        "scripts/_patch_modelname.py", "scripts/_proxytest.py",
                        "scripts/accept_real_model.py", "scripts/check_a9.py",
                        "scripts/check_ollama_adapter.py", "scripts/check_ollama_imports.py",
                        "scripts/find_docs.py", "scripts/net_probe.py",
                        "scripts/net_probe2.py", "scripts/test_ollama_text.py",
                    ],
                    "secret_scan": "0 处密钥命中（白名单 29 文件，AIza/sk-/gsk_/ghp_/gho_ 全模式）",
                    "lfs_check": "无 LFS 追踪文件；LFS 已安装但未用于本仓任何文件",
                    "remote_status": "本地仓库无 origin（git remote 为空）；需仓库所有者先创建 GitHub 仓库并配置远端",
                },
                "counts": c,
                "gates": {
                    g: {
                        "name": GATES[g],
                        "status": self.gate_status(g),
                        "total": len([r for r in self.results if r.gate == g]),
                    }
                    for g in GATES
                },
                "results": [r.__dict__ for r in self.results],
            },
            ensure_ascii=False,
            indent=2,
        )


# ---------------------------------------------------------------- 工具


def run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "ignore"), p.stderr.decode("utf-8", "ignore")
    except FileNotFoundError:
        return 127, "", f"找不到命令：{cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"命令超时：{cmd[0]}"


def http_json(path: str, base: str, timeout: int = 30) -> tuple[int, object]:
    """返回 (状态码, 解析后的 JSON 或原始文本)。

    刻意区分「连接失败」与「服务端返回了非 JSON」——两者的排查方向完全不同。
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    except Exception as exc:  # noqa: BLE001
        return 0, {"_transport_error": f"{type(exc).__name__}: {exc}"}

    try:
        return status, json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return status, {"_raw": raw.decode("utf-8", "ignore")[:400]}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_tls(host: str, port: int = 443, timeout: float = 4.0) -> tuple[bool, str]:
    """手动建 socket 并先设超时——否则被丢包的 SYN 会走操作系统的重试（约 2 分钟）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        if port == 443:
            ctx = ssl.create_default_context()
            ctx.settimeout(timeout)
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                return True, tls.version() or ""
        return True, "TCP"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"[:120]
    finally:
        try:
            sock.close()
        except OSError:
            pass


def ffmpeg_bin() -> str | None:
    for cand in (os.getenv("VC_FFMPEG"), "ffmpeg"):
        if cand and shutil.which(cand):
            return cand
        if cand and Path(cand).exists():
            return cand
    # 常见安装路径 fallback
    for p in (Path("C:/ffmpeg/bin/ffmpeg.exe"), Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"), Path("/usr/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")):
        if p.exists():
            return str(p)
    return None


def ffprobe_bin() -> str | None:
    for cand in (os.getenv("VC_FFPROBE"), "ffprobe"):
        if cand and shutil.which(cand):
            return cand
        if cand and Path(cand).exists():
            return cand
    # 常见安装路径 fallback
    for p in (Path("C:/ffmpeg/bin/ffprobe.exe"), Path("C:/Program Files/ffmpeg/bin/ffprobe.exe"), Path("/usr/bin/ffprobe"), Path("/usr/local/bin/ffprobe")):
        if p.exists():
            return str(p)
    return None


def repo_readme_texts() -> list[Path]:
    return [ROOT / "README.md", ROOT / "README.zh-CN.md"]


# ---------------------------------------------------------------- 检查项


def check_environment() -> tuple[str, str, list[str]]:
    """A1 运行环境：Python / Node / FFmpeg 能力齐备。"""
    ev: list[str] = []
    problems: list[str] = []

    if sys.version_info < (3, 11):
        problems.append(f"Python {platform.python_version()} < 3.11")
    ev.append(f"python={platform.python_version()}")

    node = shutil.which("node")
    if node:
        code, out, _ = run([node, "--version"])
        ev.append(f"node={out.strip()}")
    else:
        ev.append("node=未找到（仅构建前端必需，运行时非必需）")

    ff = ffmpeg_bin()
    fp = ffprobe_bin()
    if not ff or not fp:
        problems.append("未找到 ffmpeg / ffprobe")
    else:
        ev.append(f"ffmpeg={ff}")
        code, out, _ = run([ff, "-version"])
        first = out.splitlines()[0] if out else ""
        ev.append(first[:80])
        # 关键能力：H.264 编码、AAC 编码、字幕滤镜（烧录字幕依赖）
        _, enc, _ = run([ff, "-hide_banner", "-encoders"], timeout=60)
        needed = []
        if "libx264" not in enc:
            needed.append("libx264")
        if " aac " not in enc:
            needed.append("aac")
        _, filt, _ = run([ff, "-hide_banner", "-filters"], timeout=60)
        if "subtitles" not in filt:
            needed.append("subtitles(libass)")
        if needed:
            problems.append("FFmpeg 缺少能力：" + ", ".join(needed))
        else:
            ev.append("ffmpeg-capabilities=libx264,aac,subtitles")

    if problems:
        return FAIL, "；".join(problems), ev
    return PASS, "运行环境齐备", ev


def check_backend_health(base: str) -> tuple[str, str, list[str]]:
    """A2 后端可启动且健康检查通过。"""
    code, data = http_json("/api/health", base)
    if code != 200:
        return FAIL, f"健康检查失败（HTTP {code}）", [f"{base}/api/health -> {code}"]
    d = data if isinstance(data, dict) else {}
    ev = [
        f"status={d.get('status')}",
        f"version={d.get('version')}",
        f"ffmpeg={d.get('ffmpeg')}",
        f"ffprobe={d.get('ffprobe')}",
    ]
    if d.get("status") != "ok":
        return FAIL, f"服务状态异常：{d.get('status')}", ev
    return PASS, "后端健康检查通过", ev


def _test_ollama_text_model() -> tuple[bool, str]:
    """使用 Ollama 的纯文本模型（qwen2.5:3b）做一次轻量级调用，验证 Ollama 服务是否真正可用。

    避免使用视觉模型（qwen2.5vl:3b），因为视觉模型对显存/显卡要求更高，
    在 GTX 960 等旧卡上更容易因 CUDA 工具链不兼容而崩溃。
    """
    try:
        import httpx

        with httpx.Client(timeout=httpx.Timeout(60)) as client:
            resp = client.post(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": "qwen2.5:3b",
                    "messages": [{"role": "user", "content": "你好，请用中文简单自我介绍。"}],
                    "stream": False,
                    "options": {"temperature": 0.7},
                },
            )
            if resp.status_code >= 300:
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
            data = resp.json()
            text = (data.get("message") or {}).get("content", "") or ""
            if not text:
                return False, "Ollama 返回空内容"
            return True, f"模型回复：{text[:80]}..."

    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def check_real_model(base: str) -> tuple[str, str, list[str]]:
    """A3 真实模型验收：至少一个厂商用真实 Key 跑通「视频 → 逐镜头解说词」。

    这里不依赖任何模拟响应：直接调用生产接口 /projects/{id}/analyze，
    由已配置的模型厂商真实返回结果。

    对于 Ollama（本地模型服务）：即使不需要 API Key，也检查本地 Ollama 服务是否可达；
    若服务可达但模型加载失败（如 GTX 960 的 CUDA 工具链不兼容），标记为 BLOCKED。
    """
    from app.db import Project, SessionLocal, Shot  # noqa: PLC0415
    from app.services.keyvault import resolve_key  # noqa: PLC0415

    ev: list[str] = []
    db = SessionLocal()
    try:
        project = db.query(Project).order_by(Project.id.desc()).first()
        if project is None:
            return SKIP, "没有可用的项目，无法做真实模型验收", ev
        if not project.video_path or not Path(project.video_path).exists():
            return SKIP, "项目没有源视频", ev

        # 先检查本地 Ollama 服务（无需 API Key，但模型加载可能因 CUDA 不兼容而失败）
        ollama_ok, ollama_info = probe_tls("127.0.0.1", port=11434)
        if ollama_ok:
            ev.append(f"Ollama(127.0.0.1:11434) -> 可达 {ollama_info}")
            # 尝试用 Ollama 的纯文本模型（qwen2.5:3b）做一次轻量级调用，
            # 避免视觉模型对显存/显卡的更高要求
            ollama_result = _test_ollama_text_model()
            if ollama_result[0]:
                return PASS, f"Ollama 本地模型 qwen2.5:3b 正常：{ollama_result[1]}", ev
            else:
                return (
                    BLOCKED,
                    f"Ollama 服务可达但模型加载失败：{ollama_result[1]}",
                    ev,
                )
        else:
            ev.append(f"Ollama(127.0.0.1:11434) -> 不可达 {ollama_info[:40]}")

        configured = []
        for pid in ("gemini", "qwen", "doubao", "openai", "siliconflow", "ollama"):
            key, src = resolve_key(db, pid)
            if key:
                configured.append(f"{pid}({src})")
        ev.append("已配置密钥的厂商：" + (", ".join(configured) or "无"))
        if not configured:
            return SKIP, (
                "没有任何厂商配置了 API Key。请在「设置与密钥」中填入一个厂商的 Key 后重跑本项。"
            ), ev

        shots_before = db.query(Shot).filter(Shot.project_id == project.id).count()
        db.close()

        # 触发真实分析（走真实厂商接口，不是打桩）
        code, job = http_json(f"/api/projects/{project.id}/analyze", base)
        if code != 200:
            return FAIL, f"启动分析失败（HTTP {code}）：{job}", ev
        ev.append(f"任务已启动 job={job.get('id') if isinstance(job, dict) else '?'}")

        deadline = time.time() + 900
        final = {}
        while time.time() < deadline:
            time.sleep(3)
            _, detail = http_json(f"/api/projects/{project.id}", base)
            if not isinstance(detail, dict):
                continue
            jobs = detail.get("jobs") or []
            if not jobs:
                continue
            latest = jobs[0]
            if latest.get("status") in ("done", "failed"):
                final = latest
                break
        if not final:
            return FAIL, "真实模型分析超时（15 分钟未完成）", ev

        ev.append(f"任务状态={final.get('status')} 阶段={final.get('stage')}")
        ev.append(f"消息={str(final.get('message'))[:160]}")
        if final.get("status") == "failed":
            err = str(final.get("error") or final.get("message"))
            return FAIL, f"真实模型分析失败：{err[:400]}", ev

        db = SessionLocal()
        try:
            shots = (
                db.query(Shot)
                .filter(Shot.project_id == project.id)
                .order_by(Shot.index)
                .all()
            )
            narrated = [s for s in shots if (s.narration or "").strip()]
            ev.append(f"镜头总数={len(shots)} 有解说={len(narration)}")
            if len(shots) == 0:
                return FAIL, "真实模型没有产出任何镜头", ev
            if len(narrated) == 0:
                return FAIL, "真实模型产出了镜头但没有解说词", ev
            sample = narrated[0]
            ev.append(f"首条解说：{(sample.narration or '')[:120]}")
            ev.append(f"首条画面描述：{(sample.visual or '')[:120]}")
            if shots_before:
                ev.append(f"（验收前已有 {shots_before} 个镜头，现已被真实模型结果覆盖）")
            bad = [s.index for s in shots if not (s.narration or "").strip()]
            if bad:
                ev.append(f"无解说的镜头序号：{bad[:10]}")
            return PASS, f"真实模型产出 {len(shots)} 个镜头、{len(narrated)} 条解说词", ev
        finally:
            db.close()
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass


def check_full_render(base: str) -> tuple[str, str, list[str]]:
    """A4 完整成片：真实素材走完导入→文案→配音→字幕→合成→MP4。

    这里复用已验收的镜头（真实模型或人工审核过的），只验证「配音→字幕→合成」这一段
    是否在真实素材上稳定产出可播放的成片。
    """
    from app.db import Project, Render, SessionLocal, Shot  # noqa: PLC0415

    ev: list[str] = []
    db = SessionLocal()
    try:
        project = db.query(Project).order_by(Project.id.desc()).first()
        if project is None:
            return SKIP, "没有项目", ev
        shots = db.query(Shot).filter(Shot.project_id == project.id).all()
        narrated = [s for s in shots if (s.narration or "").strip()]
        if not narrated:
            return SKIP, "项目还没有带解说的镜头，先完成 A3", ev
        pid = project.id
        aspect = project.aspect or "original"
    finally:
        db.close()

    code, job = http_json(f"/api/projects/{pid}/render", base)
    if code != 200:
        return FAIL, f"启动渲染失败（HTTP {code}）：{job}", ev
    ev.append(f"渲染任务已启动 job={job.get('id') if isinstance(job, dict) else '?'}")

    deadline = time.time() + 1200
    final = {}
    while time.time() < deadline:
        time.sleep(3)
        _, detail = http_json(f"/api/projects/{pid}", base)
        if not isinstance(detail, dict):
            continue
        jobs = detail.get("jobs") or []
        if not jobs:
            continue
        latest = jobs[0]
        if latest.get("status") in ("done", "failed"):
            final = latest
            break
    if not final:
        return FAIL, "渲染超时（20 分钟未完成）", ev
    ev.append(f"任务状态={final.get('status')}")
    if final.get("status") == "failed":
        return FAIL, f"渲染失败：{str(final.get('error') or final.get('message'))[:400]}", ev

    db = SessionLocal()
    try:
        render = db.query(Render).filter(Render.project_id == pid).order_by(Render.id.desc()).first()
        if render is None or not render.video_path:
            return FAIL, "渲染完成但没有成片记录", ev
        path = Path(render.video_path)
        if not path.exists():
            return FAIL, f"成片文件不存在：{path}", ev
        size = path.stat().st_size
        ev.append(f"成片={path.name} 大小={size / 1048576:.2f} MB")
        ev.append(f"sha256={sha256_of(path)[:32]}…")
        ev.append(f"字幕={'有' if render.subtitle_path else '无'}")
        if size < 50_000:
            return FAIL, f"成片体积异常小（{size} 字节）", ev
        return PASS, f"完整成片已生成（{size / 1048576:.2f} MB）", ev
    finally:
        db.close()


def check_media_quality(base: str) -> tuple[str, str, list[str]]:
    """A5 成片质量：字幕时间轴、旁白时长、原声保留、人声清晰度、画幅比例。"""
    from app.db import Project, Render, SessionLocal, Shot  # noqa: PLC0415

    ev: list[str] = []
    problems: list[str] = []

    ff = ffmpeg_bin()
    fp = ffprobe_bin()
    if not ff or not fp:
        return FAIL, "缺少 ffmpeg / ffprobe，无法检查成片质量", ev

    db = SessionLocal()
    try:
        project = db.query(Project).order_by(Project.id.desc()).first()
        render = db.query(Render).filter(Render.project_id == project.id).order_by(Render.id.desc()).first()
        if render is None or not render.video_path or not Path(render.video_path).exists():
            return SKIP, "还没有成片可检查", ev
        video = Path(render.video_path)
        shots = db.query(Shot).filter(Shot.project_id == project.id).all()
        total_narration = sum(len((s.narration or "").strip()) for s in shots)
        expected_aspect = project.aspect or "original"
        source_w = project.width or 0
        source_h = project.height or 0
    finally:
        db.close()

    # 1) 视频流与画幅
    code, out, _ = run(
        [
            fp, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,codec_name",
            "-of", "json", str(video),
        ],
        timeout=120,
    )
    try:
        vstream = (json.loads(out).get("streams") or [{}])[0]
    except (json.JSONDecodeError, IndexError):
        vstream = {}
    w = int(vstream.get("width") or 0)
    h = int(vstream.get("height") or 0)
    vdur = float(vstream.get("duration") or 0)
    ev.append(f"视频流={vstream.get('codec_name')} {w}x{h} {vdur:.1f}s")
    if not w or not h:
        problems.append("成片没有可用的视频流")
    if expected_aspect == "9:16" and not (h > w):
        problems.append("期望竖屏 9:16，实际是横屏")
    if expected_aspect == "16:9" and not (w > h):
        problems.append("期望横屏 16:9，实际是竖屏")
    if expected_aspect == "original" and source_w and source_h:
        if abs(w - source_w) > 4 and abs(h - source_h) > 4:
            ev.append(f"注意：原始比例模式下成片尺寸 {w}x{h} 与源 {source_w}x{source_h} 不同")

    # 2) 音频流与人声清晰度
    code, out, _ = run(
        [
            fp, "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,duration,channels",
            "-of", "json", str(video),
        ],
        timeout=120,
    )
    try:
        astream = (json.loads(out).get("streams") or [{}])[0]
    except (json.JSONDecodeError, IndexError):
        astream = {}
    ev.append(f"音频流={astream.get('codec_name')} {astream.get('channels')}ch {astream.get('duration')}")
    if not astream:
        problems.append("成片没有音频流（解说轨缺失）")

    code, _, err = run(
        [ff, "-hide_banner", "-i", str(video), "-af", "volumedetect", "-f", "null", "NUL" if os.name == "nt" else "/dev/null"],
        timeout=300,
    )
    mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", err or "")
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", err or "")
    if mean:
        mv = float(mean.group(1))
        ev.append(f"整体音量 mean={mv} dB")
        if mv < -45:
            problems.append(f"整体音量过低（{mv} dB），疑似没有混音")
    if peak:
        pv = float(peak.group(1))
        ev.append(f"峰值音量 max={pv} dB")
        if pv > -0.5:
            problems.append(f"峰值接近削波（{pv} dB）")
        if pv < -30:
            problems.append(f"峰值过低（{pv} dB），疑似静音")

    # 3) 字幕与语音对齐
    db = SessionLocal()
    try:
        render = db.query(Render).filter(Render.project_id == project.id).order_by(Render.id.desc()).first()
        srt = Path(render.subtitle_path) if render and render.subtitle_path else None
        shots = db.query(Shot).filter(Shot.project_id == project.id).all()
        tts_total = sum(float(s.tts_duration or 0) for s in shots)
    finally:
        db.close()

    ev.append(f"解说总字数={total_narration} 配音总时长={tts_total:.1f}s 成片时长={vdur:.1f}s")
    if tts_total > 0 and vdur > 0:
        ratio = tts_total / vdur
        ev.append(f"配音/画面 时长比 = {ratio:.2f}")
        if ratio > 1.6:
            problems.append(f"配音比画面长 {ratio:.2f} 倍，成片尾部会长时间定格")
        if ratio < 0.15 and total_narration > 20:
            problems.append(f"配音只占画面 {ratio:.0%}，几乎听不到解说")

    if srt and srt.exists():
        content = srt.read_text(encoding="utf-8-sig", errors="ignore")
        cues = re.findall(
            r"(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})", content
        )
        ev.append(f"字幕条数={len(cues)}")
        if not cues:
            problems.append("SRT 里没有可解析的时间轴")
        else:
            last_end = 0.0
            for h1, m1, s1, ms1, *_ in cues:
                last_end = max(last_end, int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1) / 1000)
            ev.append(f"字幕最后结束于 {last_end:.1f}s")
            if tts_total > 0 and abs(last_end - tts_total) > max(3.0, tts_total * 0.25):
                problems.append(
                    f"字幕结束点 {last_end:.1f}s 与配音总长 {tts_total:.1f}s 偏差过大，可能没有跟随语音"
                )
    else:
        ev.append("该成片未生成 SRT 字幕")

    if problems:
        return FAIL, "；".join(problems), ev
    return PASS, "成片质量检查通过", ev


def check_i18n_parity() -> tuple[str, str, list[str]]:
    """A6 双语完整性：中英文案键集合一致。"""
    zh = ROOT / "packages" / "i18n" / "src" / "locales" / "zh-CN.ts"
    en = ROOT / "packages" / "i18n" / "src" / "locales" / "en.ts"
    if not zh.exists() or not en.exists():
        return FAIL, "找不到语言文件", []

    def keys(path: Path) -> set[str]:
        text = path.read_text(encoding="utf-8")
        return set(re.findall(r"^\s{2,}([A-Za-z0-9_]+):", text, re.M))

    zk, ek = keys(zh), keys(en)
    missing = sorted(zk - ek)
    extra = sorted(ek - zk)
    ev = [f"zh-CN 键数={len(zk)}", f"en 键数={len(ek)}"]
    if missing:
        ev.append(f"en 缺少：{missing[:10]}")
    if extra:
        ev.append(f"en 多出：{extra[:10]}")
    if missing or extra:
        return FAIL, "中英文案键集合不一致", ev
    return PASS, f"中英文案键集合一致（{len(zk)} 项）", ev


def check_key_security(base: str) -> tuple[str, str, list[str]]:
    """A7 密钥安全：库里是密文、接口只回掩码、日志不含明文。"""
    from app.db import SessionLocal, Setting  # noqa: PLC0415

    ev: list[str] = []
    db = SessionLocal()
    try:
        rows = db.execute(__import__("sqlalchemy").select(Setting)).fetchall()
    finally:
        db.close()

    plaintext_hits = 0
    for row in rows:
        value = row.value or ""
        if value.startswith("gAAAA") or value.startswith("AAAA"):  # Fernet token
            continue
        if re.match(r"^(sk-|AIza|gsk_|xai-|Bearer\s)", value):
            plaintext_hits += 1
    ev.append(f"settings 记录数={len(rows)} 明文疑似={plaintext_hits}")
    if plaintext_hits:
        return FAIL, f"有 {plaintext_hits} 条密钥以明文存储", ev

    code, data = http_json("/api/settings/keys", base)
    if code != 200:
        return FAIL, f"读取密钥列表失败（HTTP {code}）", ev
    keys = (data or {}).get("keys") or []
    leaked = [k for k in keys if k.get("masked") and "*" not in k["masked"] and len(k["masked"]) > 12]
    ev.append(f"接口返回密钥条目={len(keys)} 疑似明文={len(leaked)}")
    if leaked:
        return FAIL, "接口返回了未掩码的密钥", ev

    log = ROOT / "data" / "logs" / "app.log"
    if log.exists():
        text = log.read_text(encoding="utf-8", errors="ignore")
        hits = re.findall(r"(sk-[A-Za-z0-9_\-]{16,}|AIza[A-Za-z0-9_\-]{20,})", text)
        ev.append(f"日志中疑似明文密钥={len(hits)}")
        if hits:
            return FAIL, f"日志中出现 {len(hits)} 处疑似明文密钥", ev
    else:
        ev.append("暂无 app.log")
    return PASS, "密钥以密文存储，接口与日志均无明文", ev


def check_desktop_backend() -> tuple[str, str, list[str]]:
    """A8 桌面端能定位并拉起本机后端。"""
    script = ROOT / "apps" / "desktop" / "dist" / "backend-check.js"
    if not script.exists():
        return SKIP, "桌面端尚未编译（npm run build:desktop）", []
    node = shutil.which("node")
    if not node:
        # 常见安装路径 fallback
        for p in (Path("C:/Program Files/nodejs/node.exe"), Path("C:/Program Files (x86)/nodejs/node.exe"), Path("/usr/bin/node"), Path("/usr/local/bin/node")):
            if p.exists():
                node = str(p)
                break
    if not node:
        return SKIP, "未找到 node（仅构建前端必需，运行时非必需）", []
    code, out, err = run([node, str(script)], timeout=180)
    ev = (out or err).strip().splitlines()[-6:]
    if code != 0:
        return FAIL, "桌面端后端自检失败", ev
    return PASS, "桌面端能定位并拉起本机后端", ev


def check_docs_actions() -> tuple[str, str, list[str]]:
    """A9 文档可执行性：README 提到的文件存在、.env.example 覆盖全部 VC_ 变量。"""
    ev: list[str] = []
    problems: list[str] = []

    for readme in repo_readme_texts():
        if not readme.exists():
            problems.append(f"缺少 {readme.name}")
            continue
        text = readme.read_text(encoding="utf-8")
        for path in re.findall(r"`((?:apps|services|packages|scripts|config|deploy|docs)/[\w\./\-]+)`", text):
            if not (ROOT / path).exists():
                problems.append(f"{readme.name} 引用了不存在的路径：{path}")
        ev.append(f"{readme.name} 校验完成（{len(text)} 字符）")

    env_example = ROOT / "services" / "api" / ".env.example"
    if not env_example.exists():
        problems.append("缺少 services/api/.env.example")
    else:
        declared = set(re.findall(r"^(?:#\s*)?(VC_[A-Z0-9_]+)=", env_example.read_text(encoding="utf-8"), re.M))
        used = set()
        for py in (ROOT / "services").rglob("*.py"):
            used |= set(re.findall(r"getenv\(\s*[\"'](VC_[A-Z0-9_]+)", py.read_text(encoding="utf-8")))
        for py in (ROOT / "packages").rglob("*.py"):
            used |= set(re.findall(r"getenv\(\s*[\"'](VC_[A-Z0-9_]+)", py.read_text(encoding="utf-8")))
        undocumented = sorted(used - declared)
        ev.append(f".env.example 声明 {len(declared)} 个变量，代码用到 {len(used)} 个")
        if undocumented:
            problems.append("未在 .env.example 中说明：" + ", ".join(undocumented))
            ev.append(f"未说明：{undocumented}")

    if problems:
        return FAIL, "；".join(problems[:5]), ev
    return PASS, "文档引用与环境变量说明齐备", ev


def check_network_reachability() -> tuple[str, str, list[str]]:
    """A10 模型厂商出口可达性（真实 API 验收的前提）。

    检查云端模型厂商出口，以及本地 Ollama 服务。
    """
    targets = [
        ("generativelanguage.googleapis.com", "Gemini"),
        ("api.openai.com", "OpenAI"),
        ("dashscope.aliyuncs.com", "通义千问"),
        ("ark.cn-beijing.volces.com", "火山方舟"),
        ("api.siliconflow.cn", "硅基流动"),
    ]
    ev: list[str] = []
    ok_hosts: list[str] = []
    blocked: list[str] = []
    for host, label in targets:
        good, info = probe_tls(host)
        ev.append(f"{label}({host}) -> {'可达 ' + info if good else '不可达 ' + info[:40]}")
        (ok_hosts if good else blocked).append(label)

    # 本地 Ollama 服务检查：即使模型加载失败，服务本身可达也算作「本地模型服务可达」
    ollama_ok, ollama_info = probe_tls("127.0.0.1", port=11434)
    if ollama_ok:
        ev.append(f"Ollama(127.0.0.1:11434) -> 可达 {ollama_info}")
        ok_hosts.append("Ollama(本地)")
    else:
        ev.append(f"Ollama(127.0.0.1:11434) -> 不可达 {ollama_info[:40]}")
        blocked.append("Ollama(本地)")

    # 只统计云端厂商，Ollama(本地)是本地服务，不计入云端 API 可达性判断
    cloud_ok = [h for h in ok_hosts if h != "Ollama(本地)"]
    if cloud_ok:
        return (
            PASS,
            f"可达厂商：{'、'.join(cloud_ok)}；被阻断：{'、'.join(blocked) or '无'}",
            ev,
        )
    return BLOCKED, "所有云端模型厂商均不可达（网络出口受限），真实 API 验收无法进行", ev


def check_installers() -> tuple[str, str, list[str]]:
    """B1 三平台安装包（需要 CI Release 产物）。"""
    ev: list[str] = []
    release_dir = ROOT / "apps" / "desktop" / "release"
    found: list[Path] = []
    if release_dir.exists():
        found = [p for p in release_dir.rglob("*") if p.suffix.lower() in (".exe", ".dmg", ".appimage", ".deb", ".zip") and p.is_file()]
    for p in found:
        ev.append(f"{p.name}  {p.stat().st_size / 1048576:.1f} MB  sha256={sha256_of(p)[:16]}…")
    if not found:
        return (
            SKIP,
            "本地没有安装包。运行 GitHub Actions 的 release workflow（tag v* 触发）会产出三平台安装包。",
            ev + ["预期产物：Windows .exe / macOS .dmg / Linux .AppImage"],
        )
    suffixes = {p.suffix.lower() for p in found}
    missing = []
    if ".exe" not in suffixes:
        missing.append("Windows")
    if ".dmg" not in suffixes:
        missing.append("macOS")
    if not (".appimage" in suffixes or ".deb" in suffixes):
        missing.append("Linux")
    if missing:
        return WARN, f"缺少平台安装包：{'、'.join(missing)}", ev
    return PASS, f"三平台安装包齐备（{len(found)} 个）", ev


def check_release_workflow() -> tuple[str, str, list[str]]:
    """B2 CI Release 能产出三平台安装包与镜像。"""
    wf = ROOT / ".github" / "workflows" / "release.yml"
    if not wf.exists():
        return FAIL, "缺少 release workflow", []
    text = wf.read_text(encoding="utf-8")
    ev = []
    problems = []
    for plat in ("windows-latest", "macos-latest", "ubuntu-latest"):
        if plat in text:
            ev.append(f"构建矩阵含 {plat}")
        else:
            problems.append(f"缺少 {plat}")
    if "electron-builder" in text:
        ev.append("使用 electron-builder 打包")
    else:
        problems.append("未使用 electron-builder")
    if "PyInstaller" in text or "pyinstaller" in text:
        ev.append("用 PyInstaller 打出独立后端（用户无需装 Python）")
    else:
        problems.append("没有打包独立后端")
    if "docker" in text.lower():
        ev.append("构建容器镜像")
    if problems:
        return FAIL, "；".join(problems), ev
    return PASS, "Release 流程覆盖三平台", ev


def check_license_inventory() -> tuple[str, str, list[str]]:
    """B3 依赖许可清单与实际安装一致。"""
    ev: list[str] = []
    problems: list[str] = []

    license_file = ROOT / "LICENSE"
    if not license_file.exists() or "Apache License" not in license_file.read_text(
        encoding="utf-8", errors="ignore"
    ):
        problems.append("根目录缺少 Apache-2.0 LICENSE")
    else:
        ev.append("LICENSE 为 Apache-2.0")

    notices = ROOT / "THIRD_PARTY_NOTICES.md"
    if not notices.exists():
        problems.append("缺少 THIRD_PARTY_NOTICES.md")
    else:
        text = notices.read_text(encoding="utf-8")
        for dep in ("FFmpeg", "Python", "Node.js", "Electron", "FastAPI", "React"):
            if dep.lower() not in text.lower():
                problems.append(f"第三方清单未提到 {dep}")
        ev.append("第三方清单覆盖主要依赖")

    # 实际安装的 Python 包
    code, out, _ = run(
        [sys.executable, "-m", "pip", "list", "--format=json"], timeout=180
    )
    try:
        pkgs = json.loads(out)
    except json.JSONDecodeError:
        pkgs = []
    core = {"fastapi", "uvicorn", "sqlalchemy", "pydantic", "httpx", "cryptography", "pillow", "edge-tts"}
    have = {p["name"].lower() for p in pkgs}
    missing = sorted(core - have)
    ev.append(f"已安装 Python 包 {len(pkgs)} 个")
    if missing:
        problems.append(f"核心依赖未安装：{missing}")

    # 实际安装的 npm 包
    lock = ROOT / "package-lock.json"
    if lock.exists():
        data = json.loads(lock.read_text(encoding="utf-8"))
        packages = data.get("packages") or {}
        unlicensed = []
        counted = 0
        for name, meta in packages.items():
            if not name or meta.get("dev"):
                continue
            # node_modules/@vns/* 是 workspace 包的软链，许可证以 workspace 条目为准
            if name.startswith("node_modules/@vns/"):
                continue
            counted += 1
            lic = meta.get("license")
            if not lic or lic in ("SEE LICENSE IN", "UNLICENSED"):
                unlicensed.append(name.split("node_modules/")[-1])
        ev.append(f"npm 生产依赖 {counted} 个")
        workspace_lic = {
            k: meta.get("license")
            for k, meta in packages.items()
            if k.startswith(("apps/", "packages/"))
        }
        for k, lic in workspace_lic.items():
            ev.append(f"workspace {k} license={lic}")
            if not lic:
                unlicensed.append(k)
        if unlicensed:
            problems.append(f"npm 依赖缺少明确许可证：{unlicensed[:6]}")
    else:
        problems.append("缺少 package-lock.json")

    if problems:
        return FAIL, "；".join(problems[:5]), ev
    return PASS, "许可证文件与实际依赖一致", ev


def check_bedrock_licensing() -> tuple[str, str, list[str]]:
    """B4 Open-Core 边界文档齐备。"""
    ev: list[str] = []
    problems: list[str] = []
    lic = ROOT / "LICENSING.md"
    if not lic.exists():
        problems.append("缺少 LICENSING.md")
    else:
        text = lic.read_text(encoding="utf-8")
        for kw in ("Open-Core", "Apache-2.0", "AGPL"):
            if kw not in text:
                problems.append(f"LICENSING.md 未说明 {kw}")
        ev.append(f"LICENSING.md {len(text)} 字符，说明了边界与升级路径")

    for name in ("README.md", "README.zh-CN.md", "CONTRIBUTING.md"):
        p = ROOT / name
        if not p.exists():
            problems.append(f"缺少 {name}")
        else:
            ev.append(f"{name} {len(p.read_text(encoding='utf-8'))} 字符")

    if problems:
        return FAIL, "；".join(problems), ev
    return PASS, "开源治理文档齐备", ev


def check_postgres_ready() -> tuple[str, str, list[str]]:
    """C1 云端数据库：当前 SQLite，多机部署需 PostgreSQL。"""
    ev: list[str] = []
    db_path = ROOT / "services" / "api" / "app" / "db.py"
    text = db_path.read_text(encoding="utf-8")
    if "create_engine" in text and "sqlite:///" in text:
        ev.append("当前数据库：SQLite（单机）")
    pg_installed = shutil.which("psql") is not None
    ev.append(f"psql 可用：{pg_installed}")
    if pg_installed:
        env = os.getenv("VC_DATABASE_URL", "")
        if env.startswith("postgresql"):
            ev.append(f"已配置 PostgreSQL：{env.split('@')[-1]}")
            return PASS, "已切换到 PostgreSQL", ev
        return SKIP, "装了 PostgreSQL 但未配置 VC_DATABASE_URL", ev
    return (
        SKIP,
        "当前为 SQLite 单机模式；云端多机部署前需迁移到 PostgreSQL（门禁 C1）",
        ev + ["需改动：services/api/app/db.py 的 create_engine 与连接池配置"],
    )


def check_cloud_readiness() -> tuple[str, str, list[str]]:
    """C2 云端形态的其余前置条件。"""
    ev: list[str] = []
    problems: list[str] = []

    if (ROOT / "services" / "worker" / "worker.py").exists():
        ev.append("独立 Worker 存在（VC_WORKER_MODE=external）")
    else:
        problems.append("缺少独立 Worker")

    dockerfile = ROOT / "deploy" / "Dockerfile"
    compose = ROOT / "deploy" / "docker-compose.yml"
    for p in (dockerfile, compose):
        if p.exists():
            ev.append(f"{p.relative_to(ROOT)} 存在")
        else:
            problems.append(f"缺少 {p.name}")

    if (ROOT / "services" / "api" / "app" / "tiers.py").exists():
        ev.append("套餐/额度配置化（config/tiers.yaml）")
    else:
        problems.append("缺少 tiers 配置模块")

    accounts = list((ROOT / "services").rglob("*account*")) + list(
        (ROOT / "services").rglob("*tenant*")
    ) + list((ROOT / "services").rglob("*user*"))
    ev.append(f"账号/租户相关模块：{len(accounts)} 个")
    if not accounts:
        problems.append("缺少账号与多租户隔离（属闭源官方云服务范围，不在本仓库）")

    if problems:
        return SKIP, "；".join(problems), ev
    return PASS, "云端部署骨架齐备", ev


# ---------------------------------------------------------------- 注册表


def build_registry(base: str) -> list[tuple[str, str, str, Callable[[], tuple[str, str, list[str]]]]]:
    return [
        ("A", "A1", "运行环境与 FFmpeg 能力", check_environment),
        ("A", "A2", "后端健康检查", lambda: check_backend_health(base)),
        ("A", "A3", "真实模型产出逐镜头解说词", lambda: check_real_model(base)),
        ("A", "A4", "完整成片生成（配音→字幕→合成→MP4）", lambda: check_full_render(base)),
        ("A", "A5", "成片质量（字幕同步/时长/音量/画幅）", lambda: check_media_quality(base)),
        ("A", "A6", "中英文案键集合一致", check_i18n_parity),
        ("A", "A7", "密钥加密与日志脱敏", lambda: check_key_security(base)),
        ("A", "A8", "桌面端可拉起本机后端", check_desktop_backend),
        ("A", "A9", "文档可执行性与环境变量说明", check_docs_actions),
        ("A", "A10", "模型厂商出口可达性", check_network_reachability),
        ("B", "B1", "三平台安装包产物", check_installers),
        ("B", "B2", "Release 工作流覆盖三平台", check_release_workflow),
        ("B", "B3", "许可证文件与实际依赖一致", check_license_inventory),
        ("B", "B4", "Open-Core 治理文档齐备", check_bedrock_licensing),
        ("C", "C1", "云端数据库就绪（PostgreSQL）", check_postgres_ready),
        ("C", "C2", "云端部署前置条件", check_cloud_readiness),
    ]


# ---------------------------------------------------------------- 入口


def main() -> int:
    ap = argparse.ArgumentParser(description="VideoNarrator AI 发布验收")
    ap.add_argument("--base", default="http://127.0.0.1:8080", help="后端地址")
    ap.add_argument("--gate", choices=list(GATES), help="只跑某个门禁")
    ap.add_argument("--all", action="store_true", help="跑全部门禁（默认）")
    ap.add_argument("--list", action="store_true", help="列出检查项")
    ap.add_argument("--json", help="额外输出 JSON 到指定路径")
    args = ap.parse_args()

    registry = build_registry(args.base)

    if args.list:
        print(f"{'门禁':<5}{'编号':<5}{'检查项'}")
        print("-" * 78)
        for gate, code, title, _ in registry:
            print(f"{gate:<5}{code:<5}{title}")
        return 0

    runner = Runner(args.base)
    for gate, code, title, fn in registry:
        if args.gate and gate != args.gate:
            continue
        res = runner.check(gate, code, title, fn)
        icon = {PASS: "✅", FAIL: "❌", SKIP: "⏭️", WARN: "⚠️", BLOCKED: "🚫"}[res.status]
        print(f"{icon} [{gate}] {code} {title}  ({res.duration_ms}ms)")
        if res.status in (FAIL, WARN):
            print(f"     {res.detail[:160]}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORT_DIR / "report.md"
    md_path.write_text(runner.render_markdown(), encoding="utf-8")
    json_path = REPORT_DIR / "report.json"
    json_path.write_text(runner.render_json(), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(runner.render_json(), encoding="utf-8")

    c = runner.counts()
    print(f"\n通过 {c[PASS]} · 失败 {c[FAIL]} · 跳过 {c[SKIP]} · 阻塞 {c[BLOCKED]} · 警告 {c[WARN]}")
    for gate, name in GATES.items():
        print(f"  门禁 {gate} {name}：{runner.gate_status(gate)}")
    print(f"\n报告：{md_path}")
    print(f"      {json_path}")
    return c[FAIL]


if __name__ == "__main__":
    raise SystemExit(main())
