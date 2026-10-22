# ============================================================
#  VideoNarrator AI · 网页版镜像
#
#  构建：
#    docker build -f deploy/Dockerfile -t videonarrator/ai:latest .
#  运行：
#    docker compose -f deploy/docker-compose.yml up -d
# ============================================================

# ---------- 前端构建 ----------
FROM node:20-bookworm-slim AS web-builder
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY packages/i18n/package.json packages/i18n/
COPY packages/ui/package.json packages/ui/
RUN npm ci --workspaces --include-workspace-root
COPY apps/web apps/web
COPY packages packages
RUN npm run build:web

# ---------- 后端依赖 ----------
FROM python:3.12-slim-bookworm AS api-builder
WORKDIR /repo
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY services/api/requirements.txt services/api/requirements.txt
COPY packages/media-core packages/media-core
COPY packages/ai-providers packages/ai-providers
RUN pip install --no-cache-dir -r services/api/requirements.txt

# ---------- 运行时 ----------
FROM python:3.12-slim-bookworm AS runtime

# ffmpeg：视频处理核心；fonts-noto-cjk：烧录中文字幕
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg fonts-noto-cjk curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    VC_DATA_DIR=/data \
    VC_FRONTEND_DIST=/app/web \
    VC_SUBTITLE_FONT="Noto Sans CJK SC" \
    VC_FFMPEG=/usr/bin/ffmpeg \
    VC_FFPROBE=/usr/bin/ffprobe

WORKDIR /app

COPY --from=api-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=api-builder /usr/local/bin /usr/local/bin
COPY services/api/app /app/app
COPY packages/media-core /app/packages/media-core
COPY packages/ai-providers /app/packages/ai-providers
COPY --from=web-builder /repo/apps/web/dist /app/web
COPY config /app/config

RUN mkdir -p /data && useradd -m -u 10001 vns && chown -R vns:vns /app /data
USER vns

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
