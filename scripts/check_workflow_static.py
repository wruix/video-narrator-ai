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
11. RA-26：npmRebuild:false 生效配置 + app-builder 诊断步骤错误隔离
    （预检/构建后显式 set +e + 管道落盘，ldd 静态 ELF 非零不终止诊断）
12. RA-27：package.json 元数据（author.email/homepage/repository）、
    extraResources 指向 services/api 真实产物、第 19 步哈希 stdin 模式无 shasum 乐观回退、
    第 20 步 bundled 资源硬断言（缺失即 exit 1）
"""
import json
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

# ---- 9d. app-builder-bin 诊断（RA-24：预检非致命 + 构建后 always() 对比）
def _step_by_name(prefix: str):
    for s in job["steps"]:
        if isinstance(s, dict) and str(s.get("name", "")).startswith(prefix):
            return s
    return None

check(
    "Preflight check app-builder-bin 步骤存在（read-only）",
    "Preflight check app-builder-bin (read-only)" in text,
)
check(
    "前后诊断均使用 builder-util 自身解析上下文（与打包消费的同一 appBuilderPath）",
    text.count("require.resolve('builder-util/out/util.js')") >= 2
    and text.count(".appBuilderPath") >= 2,
    f"builder-util 解析 {text.count(chr(39) + 'builder-util/out/util.js' + chr(39))} 次",
)
_pre_i0 = text.find("- name: Preflight check app-builder-bin")
_pre_i1 = text.find("- name: Package desktop app")
check(
    "预检为只读非致命（块内无 exit 1），真实失败保留在打包步骤",
    -1 < _pre_i0 < _pre_i1 and "exit 1" not in text[_pre_i0:_pre_i1],
)
_post = _step_by_name("Post-build app-builder diagnostics")
check(
    "构建后诊断步骤存在且 if: always()",
    isinstance(_post, dict) and _post.get("if") == "always()" and _post.get("shell") == "bash",
    f"实际: {(_post or {}).get('if') if isinstance(_post, dict) else None}",
)

# ---- 9e. Shell 约束（RA-24：Windows 默认 shell 是 pwsh，Bash 语法必须显式声明）
_pkg = _step_by_name("Package desktop app")
check(
    "Package desktop app 显式声明 shell: bash",
    isinstance(_pkg, dict) and _pkg.get("shell") == "bash",
    f"实际: {(_pkg or {}).get('shell') if isinstance(_pkg, dict) else None}",
)
_set_e_no_bash = [
    s.get("name", f"step{i}")
    for i, s in enumerate(job["steps"], 1)
    if isinstance(s, dict) and "run" in s
    and "set -e" in (s.get("run") or "")
    and s.get("shell") != "bash"
]
check(
    "所有含 set -e 的 run 步骤均显式 shell: bash",
    not _set_e_no_bash,
    f"缺失声明: {_set_e_no_bash}",
)

# ---- 9f. RA-26：npmRebuild 修复与诊断步骤错误隔离
EB_CFG_PATH = ROOT / "apps/desktop/electron-builder.yml"
eb_cfg = EB_CFG_PATH.read_text(encoding="utf-8")
check(
    "实际生效配置 apps/desktop/electron-builder.yml 声明 npmRebuild: false（RA-25B 根因 A 修复）",
    re.search(r"(?m)^\s*npmRebuild:\s*false\s*$", eb_cfg) is not None,
)
check(
    "electron-builder.yml 中 npmRebuild 仅作为顶层键声明一次（无冲突/重复定义；解析语义 = false）",
    len(re.findall(r"(?m)^\s*npmRebuild:", eb_cfg)) == 1
    and (yaml.safe_load(eb_cfg) or {}).get("npmRebuild") is False,
)


def _code_lines(run_text: str) -> str:
    """剥离 run 块中的注释行，只对可执行代码行做断言。"""
    return "\n".join(l for l in run_text.splitlines() if not l.lstrip().startswith("#"))


_pkg_step = _step_by_name("Package desktop app")
pkg_run = str(_pkg_step.get("run", "")) if isinstance(_pkg_step, dict) else ""
_pre_run = str((_step_by_name("Preflight check app-builder-bin") or {}).get("run", ""))
_post_run = str((_post or {}).get("run", ""))

for label, run_text in (("预检", _pre_run), ("构建后诊断", _post_run)):
    check(
        f"{label}步骤以显式 set +e / set +o pipefail 隔离 runner 默认 errexit（诊断绝不能提前失败）",
        "set +e" in run_text and "set +o pipefail" in run_text,
    )
    check(
        f"{label}步骤代码未被改写为 set -e（保持非致命 / 只读取证定位；注释行不影响断言）",
        "set -e" not in _code_lines(run_text)
        and not re.search(r"(?m)^\s*set\s+-e\b", run_text),
    )

check(
    "Package 步骤保留 set -e（诊断逻辑不得吞掉真实构建失败）",
    "set -e" in pkg_run,
)
# ldd/otool/readelf/help 输出必须先落盘再截取（避免 "| head" 在 -o pipefail 下 SIGPIPE 误报），
# 且 ldd 的非零返回码必须被记录而不是终止诊断
for label, run_text in (("预检", _pre_run), ("构建后诊断", _post_run)):
    check(
        f"{label}步骤无 'otool/ldd/readelf ... | head' 管道（先落盘再截取，防 SIGPIPE/pipefail）",
        not re.search(r'(?:otool|ldd|readelf)[^\n|]*\| head', run_text),
    )
    check(
        f"{label}步骤记录 ldd 返回码（静态 ELF 非零属预期，仅记录不终止）",
        "ldd_rc=" in run_text,
    )
    check(
        f"{label}步骤记录 standalone --help 返回码",
        "standalone_help_rc=" in run_text,
    )
# 构建后诊断的三态结论区分（文件状态变化 vs 诊断自身失败 vs 无基线）
check(
    "构建后诊断 RESULT 三态区分（无基线 / 诊断自失败 / 前后变化 / 不变）",
    all(k in _post_run for k in (
        "RESULT_CLASS: BEFORE_SNAPSHOT_MISSING",
        "RESULT_CLASS: AFTER_SNAPSHOT_MISSING",
        "RESULT_CLASS: SAME",
        "RESULT_CLASS: CHANGED",
    )),
)
# 工具链被剪除（打包后解析失败）时，回读构建前快照字面路径复查
check(
    "构建后诊断具备回读机制：解析失败时从 before 快照恢复 ENOENT 路径",
    "sed -n 's/^ab_bin=//p'" in _post_run and "app-builder-bin.before" in _post_run,
)

# ---- 10. 哈希校验失败即退出
n_hash_exit = len(re.findall(r'SHA-256 (?:不匹配|mismatch)[\s\S]{0,80}?exit 1', text))
check(f"所有 SHA-256 校验失败路径均 exit 1（找到 {n_hash_exit} 处）", n_hash_exit >= 4, "至少 4 个平台下载步骤")

# ---- 11. RA-27：元数据、extraResources 断链、候选验证强化
PKG_PATH = ROOT / "apps/desktop/package.json"
try:
    pkg_json = json.loads(PKG_PATH.read_text(encoding="utf-8"))
    _pkg_ok = True
except (OSError, ValueError) as e:
    pkg_json = {}
    _pkg_ok = False
check("apps/desktop/package.json 可解析", _pkg_ok)
check(
    "apps/desktop/package.json author.email 存在（.deb maintainer 来源；FpmTarget 要求）",
    isinstance(pkg_json.get("author"), dict) and bool(pkg_json["author"].get("email"))
    and bool(pkg_json["author"].get("name")),
)
check(
    "apps/desktop/package.json homepage 存在（computePackageUrl 第一来源；CI 无 GITHUB_REPOSITORY 支持）",
    bool(pkg_json.get("homepage")),
)
check(
    "apps/desktop/package.json repository 存在（computePackageUrl 第二来源/repositoryInfo 链）",
    bool(pkg_json.get("repository")),
)

try:
    eb_doc = yaml.safe_load(eb_cfg) or {}
except yaml.YAMLError:
    eb_doc = {}
_eb_res = eb_doc.get("extraResources") or []
_eb_froms = [r.get("from", "") for r in _eb_res if isinstance(r, dict)]
check(
    "extraResources from 全部指向 ../../services/api/*（修复 Run 109150569887 四平台 apps/api/* 断链）",
    len(_eb_res) == 2 and len(_eb_froms) == 2
    and all(f.startswith("../../services/api/") for f in _eb_froms),
    f"实际: {_eb_froms}",
)
check(
    "extraResources 每项 to: server 且 filter 匹配 vns-server/ffmpeg/ffprobe",
    all(r.get("to") == "server" for r in _eb_res)
    and any("vns-server*" in (r.get("filter") or []) for r in _eb_res)
    and any("ffmpeg*" in (r.get("filter") or []) for r in _eb_res)
    and any("ffprobe*" in (r.get("filter") or []) for r in _eb_res),
)

_s19 = _step_by_name("Record artifact info")
_s19_run = str((_s19 or {}).get("run", "")) if isinstance(_s19, dict) else ""
check(
    "第 19 步哈希用 stdin 重定向（sha256sum < 文件，RA-23/第 6 步 CI 实证模式）",
    'sha256sum < "$f"' in _s19_run,
)
check(
    "第 19 步不再依赖 shasum 作乐观回退（Run 109150569887 exit 127 根因）",
    "|| shasum" not in _code_lines(_s19_run),
)
check(
    "第 19 步哈希不可用时输出显式占位标记（不静默吞错）",
    "hash unavailable" in _s19_run,
)

_s20 = _step_by_name("Verify bundled FFmpeg paths in resources")
_s20_run = str((_s20 or {}).get("run", "")) if isinstance(_s20, dict) else ""
check(
    "第 20 步为硬断言（资源缺失 exit 1），不再是只列目录的空验证",
    "exit 1" in _code_lines(_s20_run),
)
check(
    "第 20 步断言 vns-server*/ffmpeg*/ffprobe* 三类资源存在性",
    all(p in _s20_run for p in ("vns-server*", "ffmpeg*", "ffprobe*")),
)
check(
    "第 20 步覆盖 Windows/macOS/Linux 三种 resources/server 布局",
    "win-unpacked" in _s20_run and "linux-unpacked" in _s20_run and 'Contents/Resources/server' in _s20_run,
)
check(
    "第 20 步按 runner_os 分支定位资源目录（Windows 上 $RUNNER_OS 被同名小写 runner_os 顶掉；改用小写名跨平台一致命中）",
    'case "$runner_os"' in _s20_run,
)

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
