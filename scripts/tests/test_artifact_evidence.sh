#!/usr/bin/env bash
# RA-30 回归测试：构建证据采集缺陷修复（F1 / F2）
#
# 覆盖点：
#   F1-a  `while IFS= read -r f || [ -n "$f" ]` 保留反斜杠（不被 POSIX read 消费）
#   F1-b  末行没有换行符时仍处理最后一条记录
#   F1-c  文件名含空格时大小与 SHA-256 都正确
#   F1-d  哈希命令失败 → 非零退出（不得输出占位文本伪成功）
#   F1-e  清单为空 → 非零退出
#   F1-f  制品缺失 → 非零退出
#   F2    输出原始整数 byte 数（wc -c），不出现 ls -lh 的 187M 之类近似值
#   F2-b  vns-server / ffmpeg / ffprobe 三项各自输出整数 byte 数
#
# 用法：bash scripts/tests/test_artifact_evidence.sh
# 依赖：bash、find、wc、sha256sum（Git Bash / Linux / macOS 均可用）
# 不使用网络、凭据、真实用户数据；全部测试数据在 mktemp 临时目录内生成并清理。
set -u

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
WF="$REPO_ROOT/.github/workflows/release-candidate-check.yml"

CASES=0
FAILS=0

pass() { CASES=$((CASES + 1)); echo "  [PASS] $*"; }
fail() { CASES=$((CASES + 1)); FAILS=$((FAILS + 1)); echo "  [FAIL] $*"; }

if [ ! -f "$WF" ]; then
  echo "workflow not found: $WF" >&2
  exit 2
fi

# 从 workflow 中抽取指定 step 的 run 脚本体（去掉 YAML 缩进），直接执行真实代码。
extract_step() {
  awk -v hdr="      - name: $1" '
    $0 == hdr { inside = 1; next }
    inside && /^      - name: / { exit }
    inside { print }
  ' "$WF" \
    | awk 'body { print } /^        run: \|$/ { body = 1 }' \
    | sed 's/^          //'
}

TMPROOT=$(mktemp -d 2>/dev/null || mktemp -d -t ra30)
cleanup() { rm -rf "$TMPROOT"; }
trap cleanup EXIT

STEP19="$TMPROOT/step19.sh"
STEP20="$TMPROOT/step20.sh"
extract_step "Record artifact info" > "$STEP19"
extract_step "Verify bundled FFmpeg paths in resources" > "$STEP20"

# 静态检查只看可执行代码行（排除注释，注释中引用历史缺陷名称属正常说明）。
CODE19="$TMPROOT/step19.code.sh"
CODE20="$TMPROOT/step20.code.sh"
grep -v '^[[:space:]]*#' "$STEP19" > "$CODE19" || true
grep -v '^[[:space:]]*#' "$STEP20" > "$CODE20" || true

echo "== 静态形态检查（直接读取 workflow 抽取出的代码）=="

if grep -Fq 'while IFS= read -r f || [ -n "$f" ]' "$CODE19"; then
  pass "第 19 步使用 while IFS= read -r f || [ -n \"\$f\" ]"
else
  fail "第 19 步缺少安全读取模式（read -r + EOF 守卫）"
fi

if grep -Eq '(^|[^_[:alnum:]])while read f;' "$CODE19"; then
  fail "第 19 步仍存在未加 -r 的 while read f"
else
  pass "第 19 步不存在未加 -r 的 while read f"
fi

if grep -Fq 'ls -lh' "$CODE19"; then
  fail "第 19 步仍使用 ls -lh（人类可读近似大小）"
else
  pass "第 19 步不再使用 ls -lh"
fi

if grep -Fq 'hash unavailable' "$CODE19"; then
  fail "第 19 步仍存在 hash unavailable 占位伪成功"
else
  pass "第 19 步已取消 hash unavailable 占位"
fi

if grep -Fq 'wc -c < "$fpath"' "$CODE19"; then
  pass "第 19 步用 wc -c 读取原始字节数"
else
  fail "第 19 步未用 wc -c 读取原始字节数"
fi

if grep -Fq '^[0-9a-f]{64}$' "$CODE19"; then
  pass "第 19 步对哈希结果做 64 位十六进制严格校验"
else
  fail "第 19 步未校验哈希结果格式"
fi

if grep -Fq 'SIZE_BYTES' "$CODE20" && grep -Fq 'wc -c < "$rpath"' "$CODE20"; then
  pass "第 20 步输出 SIZE_BYTES 原始整数字节"
else
  fail "第 20 步缺少 SIZE_BYTES 整数字节输出"
fi

if grep -Fq 'case "$runner_os"' "$CODE20" && grep -Fq 'exit 1' "$CODE20"; then
  pass "第 20 步保留 runner_os 分支与硬断言 exit 1"
else
  fail "第 20 步的 runner_os 分支/硬断言被削弱"
fi

echo ""
echo "== F1-a/F1-b read 语义（反斜杠、末行无换行）=="

BS_PATH='D:\a\video-narrator-ai\apps\desktop\release\VideoNarrator AI-1.0.0-x64.exe'
GOT_BS=$(printf '%s\n' "$BS_PATH" | { while IFS= read -r f || [ -n "$f" ]; do printf '%s' "$f"; done; })
if [ "$GOT_BS" = "$BS_PATH" ]; then
  pass "反斜杠按原文保留: $GOT_BS"
else
  fail "反斜杠被改写: [$GOT_BS] != [$BS_PATH]"
fi

GOT_EOL=$(printf '%s' 'D:\a\build\last line without newline.zip' | { while IFS= read -r f || [ -n "$f" ]; do printf '%s' "$f"; done; })
if [ "$GOT_EOL" = 'D:\a\build\last line without newline.zip' ]; then
  pass "末行无换行符仍被处理: $GOT_EOL"
else
  fail "末行无换行符记录丢失或损坏: [$GOT_EOL]"
fi

echo ""
echo "== F1-c/F2 第 19 步真实执行（含空格文件名、整数字节、真实 SHA-256）=="

WS19="$TMPROOT/ws19"
REL19="$WS19/apps/desktop/release"
mkdir -p "$REL19/sub dir" "$WS19/_temp"
head -c 1024 /dev/zero | tr '\0' 'a' > "$REL19/VideoNarrator AI-1.0.0-x64.exe"
head -c 37 /dev/zero   | tr '\0' 'b' > "$REL19/has space.dmg"
head -c 13 /dev/zero   | tr '\0' 'c' > "$REL19/sub dir/thing file.zip"

OUT19=$(GITHUB_WORKSPACE="$WS19" RUNNER_TEMP="$WS19/_temp" bash -e "$STEP19" 2>&1)
RC19=$?
if [ "$RC19" -eq 0 ]; then
  pass "第 19 步在含空格文件名的最小数据集上退出码 0"
else
  fail "第 19 步退出码 $RC19（期望 0）；输出：$OUT19"
fi

if printf '%s\n' "$OUT19" | grep -Fq "$REL19/VideoNarrator AI-1.0.0-x64.exe 1024"; then
  pass "空格文件名输出精确字节 1024"
else
  fail "缺少精确字节行（1024）：$OUT19"
fi

if printf '%s\n' "$OUT19" | grep -Fq "$REL19/has space.dmg 37"; then
  pass "空格文件名输出精确字节 37"
else
  fail "缺少精确字节行（37）：$OUT19"
fi

if printf '%s\n' "$OUT19" | grep -Fq "$REL19/sub dir/thing file.zip 13"; then
  pass "子目录含空格文件名输出精确字节 13"
else
  fail "缺少子目录精确字节行（13）：$OUT19"
fi

EXP_SHA=$(sha256sum < "$REL19/VideoNarrator AI-1.0.0-x64.exe" | awk '{print $1}')
if printf '%s\n' "$OUT19" | grep -Fq "VideoNarrator AI-1.0.0-x64.exe  $EXP_SHA"; then
  pass "实际计算 SHA-256 与独立计算结果一致（$EXP_SHA）"
else
  fail "SHA-256 不一致；期望 $EXP_SHA；输出：$OUT19"
fi

if printf '%s\n' "$OUT19" | grep -Eq '^has space\.dmg  [0-9a-f]{64}$'; then
  pass "空格文件名哈希行为完整 64 位十六进制"
else
  fail "空格文件名哈希行格式异常：$OUT19"
fi

if printf '%s\n' "$OUT19" | grep -Fq 'hash unavailable'; then
  fail "输出中出现 hash unavailable 占位"
else
  pass "输出中无占位文本"
fi

if printf '%s\n' "$OUT19" | grep -Eq '[0-9]+(\.[0-9]+)?[KMG]B?\b'; then
  fail "输出中出现人类可读近似大小（KB/MB/GB）"
else
  pass "输出中无 KB/MB 近似值"
fi

echo ""
echo "== F1-d 哈希命令失败 → 必须失败 =="

WS19F="$TMPROOT/ws19f"
REL19F="$WS19F/apps/desktop/release"
mkdir -p "$REL19F" "$WS19F/_temp" "$WS19F/_fakebin"
head -c 8 /dev/zero > "$REL19F/fake artifact.exe"
printf '#!/bin/sh\nexit 1\n' > "$WS19F/_fakebin/sha256sum"
chmod +x "$WS19F/_fakebin/sha256sum"

OUT19F=$(GITHUB_WORKSPACE="$WS19F" RUNNER_TEMP="$WS19F/_temp" PATH="$WS19F/_fakebin:$PATH" bash -e "$STEP19" 2>&1)
RC19F=$?
if [ "$RC19F" -ne 0 ]; then
  pass "sha256sum 失败时第 19 步非零退出（rc=$RC19F）"
else
  fail "sha256sum 失败但第 19 步仍成功（伪成功）；输出：$OUT19F"
fi

if printf '%s\n' "$OUT19F" | grep -Fq '##[error]SHA-256'; then
  pass "哈希失败输出显式 ##[error] 标记"
else
  fail "哈希失败未输出 ##[error] 标记：$OUT19F"
fi

echo ""
echo "== F1-e 空清单 → 必须失败 =="

WS19E="$TMPROOT/ws19e"
mkdir -p "$WS19E/apps/desktop/release" "$WS19E/_temp"
OUT19E=$(GITHUB_WORKSPACE="$WS19E" RUNNER_TEMP="$WS19E/_temp" bash -e "$STEP19" 2>&1)
RC19E=$?
if [ "$RC19E" -ne 0 ]; then
  pass "release 目录无制品时非零退出（rc=$RC19E）"
else
  fail "release 目录无制品但仍成功；输出：$OUT19E"
fi

echo ""
echo "== F1-f 制品缺失 → 必须失败 =="

WS19M="$TMPROOT/ws19m"
mkdir -p "$WS19M/apps/desktop/release" "$WS19M/_temp"
STEP19M="$TMPROOT/step19m.sh"
# 仅替换清单枚举行以注入不存在的路径，其余（存在性守卫/哈希校验）仍是 workflow 原代码。
sed -E 's#^[[:space:]]*find "\$REL".*-print > "\$LIST"$#printf "%s\\n" "$REL/ghost file.exe" > "$LIST"#' "$STEP19" > "$STEP19M"
if grep -Fq 'ghost file.exe' "$STEP19M"; then
  OUT19M=$(GITHUB_WORKSPACE="$WS19M" RUNNER_TEMP="$WS19M/_temp" bash -e "$STEP19M" 2>&1)
  RC19M=$?
  if [ "$RC19M" -ne 0 ]; then
    pass "清单指向缺失文件时非零退出（rc=$RC19M）"
  else
    fail "清单指向缺失文件但仍成功；输出：$OUT19M"
  fi
  if printf '%s\n' "$OUT19M" | grep -Fq '##[error]制品缺失'; then
    pass "缺失文件输出 ##[error]制品缺失"
  else
    fail "缺失文件未输出明确错误：$OUT19M"
  fi
else
  fail "无法注入缺失文件用例（sed 未命中枚举行）"
fi

echo ""
echo "== F2-b 第 20 步真实执行（Linux 布局，三项资源整数字节）=="

WS20="$TMPROOT/ws20"
RES20="$WS20/apps/desktop/release/linux-unpacked/resources/server"
mkdir -p "$RES20" "$WS20/_temp"
head -c 100 /dev/zero | tr '\0' 'x' > "$RES20/vns-server"
head -c 200 /dev/zero | tr '\0' 'y' > "$RES20/ffmpeg"
head -c 300 /dev/zero | tr '\0' 'z' > "$RES20/ffprobe"

OUT20=$(GITHUB_WORKSPACE="$WS20" RUNNER_TEMP="$WS20/_temp" runner_os=Linux bash -e "$STEP20" 2>&1)
RC20=$?
if [ "$RC20" -eq 0 ]; then
  pass "第 20 步退出码 0（资源齐备）"
else
  fail "第 20 步退出码 $RC20（期望 0）；输出：$OUT20"
fi

for pair in "vns-server:100" "ffmpeg:200" "ffprobe:300"; do
  name=${pair%%:*}
  size=${pair##*:}
  if printf '%s\n' "$OUT20" | grep -Fq "SIZE_BYTES $size $RES20/$name"; then
    pass "$name 输出 SIZE_BYTES $size"
  else
    fail "$name 未输出精确字节 $size：$OUT20"
  fi
done

if printf '%s\n' "$OUT20" | grep -Eq '^SIZE_BYTES [0-9]+ '; then
  pass "SIZE_BYTES 行均为整数"
else
  fail "SIZE_BYTES 行缺失或非整数：$OUT20"
fi

echo ""
echo "== F2-c 第 20 步资源缺失 → 必须失败（硬断言未被削弱）=="

WS20M="$TMPROOT/ws20m"
RES20M="$WS20M/apps/desktop/release/linux-unpacked/resources/server"
mkdir -p "$RES20M" "$WS20M/_temp"
head -c 10 /dev/zero > "$RES20M/vns-server"
head -c 10 /dev/zero > "$RES20M/ffmpeg"
OUT20M=$(GITHUB_WORKSPACE="$WS20M" RUNNER_TEMP="$WS20M/_temp" runner_os=Linux bash -e "$STEP20" 2>&1)
RC20M=$?
if [ "$RC20M" -ne 0 ]; then
  pass "缺少 ffprobe 时非零退出（rc=$RC20M）"
else
  fail "缺少 ffprobe 仍通过（硬断言被削弱）；输出：$OUT20M"
fi

echo ""
echo "================================================================"
echo "共 $CASES 项，失败 $FAILS 项"
if [ "$FAILS" -ne 0 ]; then
  exit 1
fi
echo "全部通过。"
exit 0
