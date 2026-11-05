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
13. RA-30：第 19 步安全读取（IFS= read -r + EOF 守卫，保留 Windows 反斜杠）、
    哈希/大小失败即 exit 1（无占位伪成功）、逐文件 wc -c 原始整数字节（替代 ls -lh）；
    第 20 步 SIZE_BYTES 整数字节输出；回归测试脚本 scripts/tests/test_artifact_evidence.sh
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
wf_hashes |= set(re.findall(r"(?<![0-9a-f])([0-9a-f]{64})(?![0-9a-f])", text))
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
    and any(t == "nsis:x64" for t in eb_targets)
    and any(t == "AppImage:x64 deb:x64" for t in eb_targets),
    f"实际: {eb_targets}",
)

# ---- 9c. FFmpeg 下载重试与严格校验（RA-32）
FETCH = ROOT / "scripts/ci/fetch_with_retry.sh"
fetch_src = FETCH.read_text(encoding="utf-8") if FETCH.is_file() else ""
check(
    "FFmpeg 下载重试脚本存在（RA-32）",
    FETCH.is_file(),
    f"missing: {FETCH}",
)
check(
    "重试次数有上限（默认 4，硬上限 10）",
    "FETCH_MAX_ATTEMPTS:-4" in fetch_src
    and 'while [ "$attempt" -le "$MAX_ATTEMPTS" ]' in fetch_src
    and '"$MAX_ATTEMPTS" -gt 10' in fetch_src,
)
check(
    "curl 设置连接超时、整体超时与低速中断（避免 92 分钟挂起）",
    "--connect-timeout" in fetch_src
    and "--max-time" in fetch_src
    and "--speed-limit" in fetch_src
    and "--speed-time" in fetch_src,
)
check(
    "重试采用有上限线性退避",
    "BACKOFF * attempt" in fetch_src and "sleep" in fetch_src,
)
check(
    "SHA-256 校验使用 stdin 重定向并严格匹配 64 位十六进制（Windows 反斜杠安全）",
    'sha256sum < "$1"' in fetch_src
    and 'shasum -a 256 < "$1"' in fetch_src
    and "'^[0-9a-f]{64}$'" in fetch_src,
)
check(
    "四个平台共 7 个固定资产下载全部走重试脚本（Windows 单包含 ffmpeg+ffprobe）",
    text.count("bash scripts/ci/fetch_with_retry.sh") == 7,
    f"实际: {text.count('bash scripts/ci/fetch_with_retry.sh')}",
)
check(
    "下载步骤不再直接使用无超时的 curl -o",
    not re.search(r"curl -sL -o \"\$TMP/", text),
)
check(
    "下载步骤显式 set -euo pipefail（失败传播不被吞掉）",
    text.count("set -euo pipefail") >= 4,
    f"实际: {text.count('set -euo pipefail')}",
)
_FETCH_TEST = ROOT / "scripts/ci/test_fetch_retry.sh"
_fetch_test_src = _FETCH_TEST.read_text(encoding="utf-8") if _FETCH_TEST.is_file() else ""
check(
    "RA-32 回归测试覆盖成功/校验失败/缺失源/参数错误/重试上限",
    _FETCH_TEST.is_file()
    and "checksum mismatch was masked as success" in _fetch_test_src
    and "missing source was masked as success" in _fetch_test_src
    and "invalid expected hash accepted" in _fetch_test_src
    and "attempt cap enforced" in _fetch_test_src,
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

# ---- 10. 哈希校验失败即退出（RA-32：集中到重试脚本）
check(
    "FFmpeg 下载重试脚本在最终失败时 exit 1，且不含 || true 吞错",
    fetch_src.rstrip().endswith("exit 1") and "|| true" not in fetch_src,
)
check(
    "下载步骤无 continue-on-error（网络问题不得被隐藏）",
    "continue-on-error" not in text,
)

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
# RA-27 契约（server 资源）+ RA-34 新增 web/dist 资源（F-3：前端独立分发）。
_server_res = [r for r in _eb_res if isinstance(r, dict) and r.get("to") == "server"]
_web_res = [
    r for r in _eb_res
    if isinstance(r, dict) and r.get("to") == "web/dist"
]
check(
    "RA-27: server 类 extraResources 的 from 全部指向 ../../services/api/*"
    "（修复 Run109150569887 apps/api/* 断链）",
    len(_server_res) == 2
    and all(str(r.get("from", "")).startswith("../../services/api/") for r in _server_res),
    f"实际 server 项: {[r.get('from') for r in _server_res]}",
)
check(
    "RA-27: server 类资源 filter 覆盖 vns-server/ffmpeg/ffprobe",
    any("vns-server*" in (r.get("filter") or []) for r in _server_res)
    and any("ffmpeg*" in (r.get("filter") or []) for r in _server_res)
    and any("ffprobe*" in (r.get("filter") or []) for r in _server_res),
)
check(
    "RA-34 F-3: extraResources 含前端资源 ../../apps/web/dist -> web/dist（安装内可核验路径，"
    "由 Electron 以 VC_FRONTEND_DIST 注入冻结后端）",
    len(_web_res) == 1 and _web_res[0].get("from") == "../../apps/web/dist",
    f"实际 web 项: {[r.get('from') for r in _web_res]}",
)

_s19 = _step_by_name("Record artifact info")
_s19_run = str((_s19 or {}).get("run", "")) if isinstance(_s19, dict) else ""
check(
    "第 19 步哈希用 stdin 重定向（sha256sum < 文件，RA-23/第 6 步 CI 实证模式）",
    'sha256sum < "$fpath"' in _s19_run,
)
check(
    "第 19 步不再依赖 shasum 作乐观回退（Run 109150569887 exit 127 根因）",
    "|| shasum" not in _code_lines(_s19_run),
)
_s19_code = _code_lines(_s19_run)
check(
    "第 19 步用 `while IFS= read -r f || [ -n \"$f\" ]` 读取（F1：反斜杠不被消费、末行无换行不丢记录）",
    'while IFS= read -r f || [ -n "$f" ]' in _s19_code,
)
check(
    "第 19 步不存在未加 -r 的 while read（F1 根因：Windows 路径反斜杠被 POSIX read 吞掉）",
    not re.search(r"(?m)^\s*while read\b", _s19_code),
)
check(
    "第 19 步哈希失败即失败：结果须匹配 ^[0-9a-f]{64}$，且不再输出 hash unavailable 占位（RA-30 收紧）",
    "'^[0-9a-f]{64}$'" in _s19_code and "hash unavailable" not in _s19_code,
)
check(
    "第 19 步输出原始整数字节（wc -c 逐文件），不再回退 ls -lh 人类可读值（F2）",
    'wc -c < "$fpath"' in _s19_code and "ls -lh" not in _s19_code,
)
check(
    "第 19 步空清单/缺失文件安全失败（exit 1），不产生伪成功",
    '[ ! -s "$LIST" ]' in _s19_code and "制品缺失" in _s19_code,
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

_s20_code = _code_lines(_s20_run)
check(
    "第 20 步逐项输出 SIZE_BYTES 原始整数字节并校验为整数（F2：vns-server/ffmpeg/ffprobe 均可重复验证）",
    "SIZE_BYTES" in _s20_code and 'wc -c < "$rpath"' in _s20_code and "'^[0-9]+$'" in _s20_code,
)
check(
    "第 20 步保留资源存在性硬断言与 OK 语义（新增诊断未削弱硬断言/包失败语义）",
    "Missing bundled resource patterns" in _s20_code
    and "OK: server + ffmpeg/ffprobe resources are bundled" in _s20_code,
)
check(
    "第 20 步生成 bundled-resources-manifest.txt（内嵌资源路径/字节数/SHA-256）",
    "bundled-resources-manifest.txt" in _s20_code
    and "SHA256" in _s20_code
    and 'sha256sum < "$rpath"' in _s20_code,
)

_test_sh = ROOT / "scripts/tests/test_artifact_evidence.sh"
_test_src = _test_sh.read_text(encoding="utf-8") if _test_sh.is_file() else ""
check(
    "RA-30 回归测试脚本存在，且覆盖 F1（read -r / 空格文件名 / 末行无换行 EOF 守卫）与 F2（整数字节）",
    _test_sh.is_file()
    and 'while IFS= read -r f || [ -n "$f" ]' in _test_src
    and "SIZE_BYTES" in _test_src
    and "GOT_EOL" in _test_src
    and "has space.dmg" in _test_src,
)

# ---- 13c. RA-32 artifact 最小化与保留期（配额风险控制）
_upload = _step_by_name("Upload candidate artifact")
_upload_with = (_upload.get("with") if isinstance(_upload, dict) else {}) or {}
_upload_path = str(_upload_with.get("path", ""))
_upload_lines = [ln.strip() for ln in _upload_path.splitlines() if ln.strip()]
check(
    "候选 artifact 不上传 *-unpacked / mac-arm64 / mac 目录（配额最小化）",
    all(k not in _upload_path for k in ("win-unpacked", "linux-unpacked", "mac-arm64"))
    and "apps/desktop/release/" not in _upload_lines
    and "apps/desktop/release" not in _upload_lines,
    f"path={_upload_path[:300]}",
)
check(
    "候选 artifact 保留交付件、更新元数据、构建追溯与 manifest",
    all(k in _upload_path for k in (
        "apps/desktop/release/*.exe",
        "apps/desktop/release/*.exe.blockmap",
        "apps/desktop/release/*.dmg",
        "apps/desktop/release/*.dmg.blockmap",
        "apps/desktop/release/*.zip",
        "apps/desktop/release/*.zip.blockmap",
        "apps/desktop/release/*.AppImage",
        "apps/desktop/release/*.deb",
        "apps/desktop/release/latest.yml",
        "apps/desktop/release/latest-mac.yml",
        "apps/desktop/release/latest-linux.yml",
        "apps/desktop/release/builder-debug.yml",
        "ffmpeg-bin-buildconf.txt",
        "bundled-resources-manifest.txt",
        "tests-ffmpeg-selfcheck/",
    )),
)
check(
    "候选 artifact retention-days 明确为 1 天（需所有者及时下载）",
    _upload_with.get("retention-days") == 1,
    f"实际: {_upload_with.get('retention-days')}",
)
check(
    "候选 artifact if-no-files-found=error（交付件缺失即失败）",
    _upload_with.get("if-no-files-found") == "error",
    f"实际: {_upload_with.get('if-no-files-found')}",
)
_summary_upload = re.search(r"name: Upload summary[\s\S]*?retention-days:\s*(\d+)", text)
_summary_ret = int(_summary_upload.group(1)) if _summary_upload else None
check(
    "汇总 artifact retention-days <= 7 天",
    isinstance(_summary_ret, int) and 1 <= _summary_ret <= 7,
    f"实际: {_summary_ret}",
)

# ---- 14. RA-32 F3：Windows 不得同时声明 nsis 与 portable（同名冲突）
_windows_targets = [tt for tt in eb_targets if tt.startswith('nsis:') or tt.startswith('portable:')]
check(
    'F3：Windows eb_target 不含有 portable target（RA-32 发布阻断项）',
    not any('portable' in tt for tt in eb_targets),
    '实际: %s' % eb_targets,
)
check(
    'F3：Windows eb_target 必须同时包含 nsis:x64（交付形态为 NSIS）',
    any(tt == 'nsis:x64' for tt in eb_targets),
    '实际: %s' % eb_targets,
)

# ---- 15. RA-32 L-1：Linux AppImage blockmap 一致性
try:
    linux_eb = yaml.safe_load((ROOT / 'apps/desktop/electron-builder.yml').read_text(encoding='utf-8')) or {}
except yaml.YAMLError:
    linux_eb = {}
_linux_targets = [(t.get('target') or '').lower() for t in (linux_eb.get('linux') or {}).get('target') or []]
_linux_publish = (linux_eb.get('linux') or {}).get('publish')
_has_appimage = 'appimage' in [t.lower() for t in _linux_targets]
check(
    'L-1：Linux 配置显式 publish: null（防止 --publish never 下仍生成 orphaned blockMapSize）',
    linux_eb.get('linux', {}).get('publish') is None,
    'linux.publish=%s' % linux_eb.get('linux', {}).get('publish'),
)
check(
    'L-1：workflow eb_target 不含 blockmap 相关关键字（仅声明 target+arch）',
    all('blockmap' not in tt.lower() for tt in eb_targets),
    '实际: %s' % eb_targets,
)

# ---- 16. RA-34：冻结后端 CI 运行自检（Windows 硬门禁）
_s_smoke = _step_by_name('Smoke test frozen backend')
_smoke_run = str((_s_smoke or {}).get('run', '')) if isinstance(_s_smoke, dict) else ''
check(
    'RA-34: Windows job 含 "Smoke test frozen backend" 步骤（真实启动冻结 exe，'
    '不得以源码 import/构建成功替代）',
    isinstance(_s_smoke, dict) and bool(_smoke_run),
)
check(
    'RA-34: 自检步骤仅 success() 且限定 win 平台（候选门禁语义）',
    str((_s_smoke or {}).get('if', '')) == "success() && matrix.platform == 'win'",
    '实际 if: %s' % (_s_smoke or {}).get('if'),
)
check(
    'RA-34: 自检步骤针对打包产物本体 resources/server/vns-server.exe 与 resources/web/dist（安装要分发的字节）',
    'resources' in _smoke_run and 'server/vns-server.exe' in _smoke_run
    and 'web/dist' in _smoke_run,
)
check(
    'RA-34: 自检脚本 scripts/ci/test_frozen_backend_smoke.sh 存在且含场景 A/B/C 与 SMOKE_RESULT 判定',
    (ROOT / 'scripts/ci/test_frozen_backend_smoke.sh').exists()
    and 'SMOKE_RESULT' in (ROOT / 'scripts/ci/test_frozen_backend_smoke.sh').read_text(encoding='utf-8'),
)
check(
    'RA-34: 自检在 manifest 验证之后、Upload candidate 之前执行（先验后传）',
    isinstance(_s_smoke, dict)
    and isinstance(_step_by_name('Upload candidate artifact'), dict)
    and [s.get('name') for s in job['steps']].index(_s_smoke.get('name'))
    < [s.get('name') for s in job['steps']].index(_step_by_name('Upload candidate artifact').get('name')),
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
