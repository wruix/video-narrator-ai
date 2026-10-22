#!/usr/bin/env bash
# AI 视频解说工作站 · Linux / macOS 启动脚本
#
# 用法：
#   ./scripts/start.sh              # 监听 127.0.0.1:8080
#   ./scripts/start.sh 0.0.0.0 8080 # 监听所有网卡（局域网可访问）
set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-8080}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/services/api/.venv"

cd "$ROOT"

# ---- 载入 services/api/.env ----
if [[ -f services/api/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source services/api/.env
  set +a
  echo "已载入 services/api/.env"
fi

# ---- 检查 FFmpeg ----
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "警告：未找到 ffmpeg / ffprobe" >&2
  echo "  Debian/Ubuntu : sudo apt install ffmpeg" >&2
  echo "  CentOS/RHEL   : sudo dnf install ffmpeg" >&2
  echo "  macOS         : brew install ffmpeg" >&2
  echo "  或在 services/api/.env 里设置 VC_FFMPEG / VC_FFPROBE 的绝对路径" >&2
fi

# ---- 检查中文字体（烧录字幕需要）----
if ! fc-list 2>/dev/null | grep -qiE "noto.*cjk|wqy|source han"; then
  echo "提示：未检测到中文字体，烧录字幕可能出现方块" >&2
  echo "  Debian/Ubuntu : sudo apt install fonts-noto-cjk" >&2
  echo "  或在 services/api/.env 里设置 VC_SUBTITLE_FONT 为已安装的中文字体名" >&2
fi

# ---- 准备虚拟环境 ----
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "未找到虚拟环境，正在创建…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip --quiet
  "$VENV/bin/pip" install -r services/api/requirements.txt --quiet
  echo "依赖安装完成"
fi

# ---- 前端构建产物 ----
if [[ ! -f apps/web/dist/index.html ]]; then
  echo "前端尚未构建"
  if command -v npm >/dev/null 2>&1; then
    (cd apps/web && npm install --no-audit --no-fund && npm run build)
  else
    echo "  未找到 npm，请手动构建前端或拷贝 apps/web/dist" >&2
  fi
fi

echo ""
echo "  VideoNarrator AI · AI 视频解说工作站"
echo "  服务地址： http://${HOST}:${PORT}"
echo "  数据目录： ${VC_DATA_DIR:-$ROOT/data}"
echo ""

cd services/api
exec "$VENV/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
