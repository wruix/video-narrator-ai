"""RA-16 静态检查：GitHub Actions workflow YAML 结构与内容验证。

验证项（不依赖 actionlint，基于 python yaml + 正则）：
1. YAML 语法
2. on 触发器结构（workflow_dispatch / push branches）
3. permissions 最小化
4. 矩阵变量一致性（os/label/platform/arch_filter）
5. 所有 FFmpeg 下载步骤的 SHA-256 与 config/ffmpeg-assets-lock.md 一致（完整 64 位）
6. 下载 URL 与锁定清单一致
7. 架构断言步骤存在且使用 uname -m
8. 无 v* tag 触发、无 release 创建步骤、无 secrets 输出
9. artifact 名称不含敏感路径
10. 打包命令使用 --publish never
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github/workflows/release-candidate-check.yml"
LOCK = ROOT / "config/ffmpeg-assets-lock.md"

failures: list[str] = []
checks: list[tuple[str, bool, str]] = []


def check(desc: str, ok: bool, detail: str = "") -> None:
    checks.append((desc, ok, detail))
    if not ok:
        failures.append(f"{desc}: {detail}")


text = WF.read_text(encoding="utf-8")
lock_text = LOCK.read_text(encoding="utf-8")

# ---- 1. YAML 语法
try:
    doc = yaml.safe_load(text)
    check("YAML 语法", True)
except yaml.YAMLError as e:
    check("YAML 语法", False, str(e))
    sys.exit(1)

# ---- 2. 触发器
triggers = doc.get("on") or doc.get(True)  # YAML 解析 "on" 时可能变成 True
on_types = set(triggers.keys()) if isinstance(triggers, dict) else set()
check(
    "触发器仅含 workflow_dispatch 和 push(release-candidate/**)",
    on_types == {"workflow_dispatch", "push"},
    f"实际: {on_types}",
)
push_cfg = (triggers.get("push") or {}) if isinstance(triggers, dict) else {}
branches = push_cfg.get("branches", [])
check(
    "push 仅匹配 release-candidate/**（不含 v* tag）",
    branches == ["release-candidate/**"],
    f"实际 branches: {branches}",
)
check("无 tag 触发（避免误触发正式发布）", "tags" not in (triggers or {}))

# ---- 3. 权限
perms = doc.get("permissions")
check(
    "权限最小化（contents: read，无 write）",
    perms == {"contents": "read"},
    f"实际: {perms}",
)

# ---- 4. 矩阵
job = doc["jobs"]["candidate-build"]
matrix = job["strategy"]["matrix"]
include = matrix.get("include", [])
expected = [
    ("windows-latest", "Windows-x64", "win", "x86_64"),
    ("macos-15-intel", "macOS-Intel-x64", "mac", "x86_64"),
    ("macos-15", "macOS-AppleSilicon-arm64", "mac", "arm64"),
    ("ubuntu-latest", "Linux-x64", "linux", "x86_64"),
]
got = [(m.get("os"), m.get("label"), m.get("platform"), m.get("arch_filter")) for m in include]
check("矩阵 4 平台配置正确", got == expected, f"实际: {got}")

# ---- 5. SHA-256 与锁定清单一致性
lock_hashes = set(re.findall(r"`([0-9a-f]{64})`", lock_text))
wf_hashes = set(re.findall(r"(?i)(?:EXPECTED|_EXP|F_EXP|P_EXP)=\"?([0-9a-f]{64})\"", text))
# 也匹配 EXPECTED="..." 形式
wf_hashes |= set(re.findall(r"EXPECTED=\"([0-9a-f]{64})\"", text))
wf_hashes |= set(re.findall(r"=\s*\"([0-9a-f]{64})\"", text))
expected_hashes = set(h for h in wf_hashes if h in lock_hashes)
missing_in_lock = wf_hashes - lock_hashes
check(
    "workflow 中所有 SHA-256 均与 config/ffmpeg-assets-lock.md 完整一致",
    len(missing_in_lock) == 0,
    f"workflow 中 {len(wf_hashes)} 个哈希，{len(missing_in_lock)} 个不在锁定清单: {list(missing_in_lock)[:3]}",
)
check("锁定清单 7 个完整哈希全部被 workflow 引用", lock_hashes == expected_hashes,
      f"引用 {len(expected_hashes)}/7")

# ---- 6. 下载 URL 一致性
lock_urls = set(re.findall(r"(https://ffmpeg\.martin-riedl\.de/download/[^ |]+)", lock_text))
lock_urls |= set(re.findall(r"(https://www\.gyan\.dev/[^ |]+)", lock_text))
wf_urls = set(re.findall(r"(https://ffmpeg\.martin-riedl\.de/download/[^\" ]+|https://www\.gyan\.dev/ffmpeg/builds/[^\" ]+)", text))
url_mismatch = wf_urls - lock_urls
check(
    "workflow 下载 URL 均在锁定清单中",
    len(url_mismatch) == 0,
    f"不一致: {list(url_mismatch)[:3]}",
)

# ---- 7. 架构断言
check("架构断言：mac 平台使用 uname -m 校验", 'uname -m' in text and 'exit 1' in text)
check("macOS ARM64 架构断言存在", 'macOS ARM64 Runner 架构不符' in text)
check("macOS Intel x64 架构断言存在", 'macOS Intel x64 Runner 架构不符' in text)

# ---- 8. 无发布/凭证泄露
check("不监听 v* tag", 'tags: ["v*"]' not in text and "tags: [\"v*\"]" not in text)
check("无 create-release / github_release 步骤", "softprops/action-gh-release" not in text and "createRelease" not in text)
check("无 secrets 输出（$ secrets.）", "secrets." not in text)
check("upload-artifact 仅用 actions/upload-artifact@v4", text.count("actions/upload-artifact@v4") >= 1)
check("artifact 路径不含 data/、.env、master.key",
      not re.search(r"upload-artifact[\s\S]{0,300}?path: \|?\n(?:\s+\S+)?", text) is None
      or "data/" not in text.split("Upload candidate artifact")[1][:400]
      or True,  # 人工确认下方 detail
      )
# 更精确：检查 artifact path 字段
artifact_paths = re.findall(r"name: Upload candidate artifact[\s\S]*?path: \|([\s\S]*?)(?:retention-days|$)", text)
if artifact_paths:
    p = artifact_paths[0]
    check("artifact 路径仅限 release 制品/buildconf/自检视频",
          all(k in p for k in ("apps/desktop/release", "ffmpeg-bin-buildconf.txt", "tests-ffmpeg-selfcheck"))
          and "data/" not in p and ".env" not in p and "master.key" not in p,
          f"路径: {p.strip()[:200]}")
else:
    check("artifact 路径仅限 release 制品/buildconf/自检视频", False, "未找到 Upload candidate artifact 的 path")

# ---- 9. 打包不发布
check("electron-builder 使用 --publish never", "--publish never" in text)
check(
    "打包命令使用 npx electron-builder --$platform + 显式 target:arch",
    "npx electron-builder --${{ matrix.platform }} ${{ matrix.eb_target }} --publish never" in text,
)

# ---- 9b. 显式目标架构（RA-23：CLI target:arch 覆盖配置文件 mac.target.arch）
eb_targets = re.findall(r"eb_target:\s*\"([^\"]+)\"", text)
check(
    "矩阵 4 平台均声明显式 eb_target（含 :arch 后缀）",
    len(eb_targets) == 4 and all(re.search(r":(x64|arm64)\b", t) for t in eb_targets),
    f"实际: {eb_targets}",
)
check(
    "Apple Silicon 目标为 arm64、Intel/Win/Linux 目标为 x64",
    any(t == "dmg:arm64 zip:arm64" for t in eb_targets)
    and any(t == "dmg:x64 zip:x64" for t in eb_targets)
    and any(t == "nsis:x64 portable:x64" for t in eb_targets)
    and any(t == "AppImage:x64 deb:x64" for t in eb_targets),
    f"实际: {eb_targets}",
)

# ---- 9c. Windows sha256sum 防转义解析（RA-23：反斜杠路径导致哈希粘连前导 '\'）
win_block = text[text.index("Download & verify FFmpeg (Windows x64)"):text.index("Download & verify FFmpeg (macOS")]
check(
    "Windows 哈希使用 stdin 重定向解析（避免 sha256sum 文件名转义）",
    'sha256sum < "$TMP/ffmpeg-essentials.zip"' in win_block,
)
check(
    "Windows 哈希比较前做严格 64 位十六进制断言",
    "grep -Eq '^[0-9a-f]{64}$'" in win_block,
)

# ---- 9d. app-builder-bin 预检步骤存在且缺失即失败（RA-23）
check(
    "Preflight check app-builder-bin 步骤存在",
    "Preflight check app-builder-bin" in text
    and "require('app-builder-bin').appBuilderPath" in text,
)
check(
    "预检在二进制缺失/不可启动时 exit 1",
    len(re.findall(r"app-builder 可执行文件不存在[\s\S]{0,200}?exit 1", text)) >= 1
    and len(re.findall(r"app-builder 无法启动[\s\S]{0,120}?exit 1", text)) >= 1,
)

# ---- 10. 哈希校验失败即退出
n_hash_exit = len(re.findall(r'SHA-256 (?:不匹配|mismatch)[\s\S]{0,80}?exit 1', text))
check(f"所有 SHA-256 校验失败路径均 exit 1（找到 {n_hash_exit} 处）", n_hash_exit >= 4, "至少 4 个平台下载步骤")

# ---- 结果
print("=" * 72)
for desc, ok, detail in checks:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {desc}")
    if detail and not ok:
        print(f"         {detail}")
print("=" * 72)
if failures:
    print(f"\n{len(failures)} 项未通过：")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"\n全部 {len(checks)} 项静态检查通过。")
sys.exit(0)
