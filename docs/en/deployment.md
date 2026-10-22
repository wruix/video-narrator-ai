# Deployment Guide

[English](deployment.md) · [简体中文](../zh-CN/deployment.md)

---

## 1. Two shapes

| | Desktop | Web server |
| --- | --- | --- |
| Where video is processed | On your machine | On the server |
| Does the video leave your machine | No | Yes (it is uploaded) |
| Model keys | Your own (BYOK) | User-supplied or platform-managed |
| Installation | Installer + FFmpeg | A browser |
| Best for | Individuals, sensitive footage, batch work | Teams, collaboration, zero-install |

Both share the same frontend and backend code — only the entry point differs.

---

## 2. Desktop

### From a release

| Platform | Artifact |
| --- | --- |
| Windows x64 | `VideoNarrator AI-<version>-x64.exe` (NSIS) or the portable build |
| macOS | `VideoNarrator AI-<version>-{x64,arm64}.dmg` |
| Linux x64 | `VideoNarrator AI-<version>-x64.AppImage` / `.deb` |

The installer bundles a standalone backend binary, so **Python is not required** —
but **FFmpeg must be installed** on the system (the Windows installer checks for it).

### From source

```bash
npm install
npm run build:web
npm run build:desktop
cd apps/desktop && npm start
```

The shell looks for a backend in this order:

1. the bundled `resources/server/vns-server`
2. the repo virtualenv `services/api/.venv`
3. system `python3` with the dependencies installed

---

## 3. Web server

### Docker (recommended)

```bash
cp config/tiers.example.yaml config/tiers.yaml
cp deploy/docker-compose.yml .
export VC_ACCESS_TOKEN="$(openssl rand -hex 24)"
docker compose up -d
```

Data persists in the `vns-data` volume (`/data` inside the container).

### Without Docker

```bash
./scripts/start.sh 0.0.0.0 8080        # Linux / macOS
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Port 8080   # Windows
```

---

## 4. Public deployment checklist

Work through this before the service is reachable by anyone but you.

### 4.1 Access token (mandatory)

```ini
VC_ACCESS_TOKEN=<a long random string>
```

Without it anyone can call your endpoints, spend your model credits, and upload
material to your machine. The UI prompts for the token automatically; you can also send
`Authorization: Bearer <token>` or append `?token=` to media URLs.

### 4.2 HTTPS (mandatory)

Plain HTTP leaks uploaded footage and rendered videos. Put Nginx / Caddy / a hosting
panel in front:

```nginx
server {
    listen 443 ssl http2;
    server_name narration.example.com;

    client_max_body_size 4096m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;      # renders can take a long time
        proxy_send_timeout 3600s;
    }
}
```

### 4.3 Tighten CORS

```ini
VC_CORS_ORIGINS=https://narration.example.com
```

### 4.4 Key strategy

| Scenario | Approach |
| --- | --- |
| Personal / small team | Mode A — each user supplies their own key and pays their own provider |
| Hosted service | Mode B — store keys as "platform-managed", or inject `VC_SERVER_KEY_*` env vars |

In Mode B, pair the keys with rate limiting and quotas so one job cannot exhaust the
credit.

### 4.5 Resources and storage

| Item | Guidance |
| --- | --- |
| CPU | 4 cores or more (encoding is CPU bound) |
| Memory | 4 GB minimum; 8 GB for 4K footage |
| Disk | Size `VC_DATA_DIR` for the renders; `work/` can be pruned regularly |
| Bandwidth | Uploads are the bottleneck; move finished videos to object storage |

### 4.6 Retention

`data/` accumulates uploads, keyframes, voice clips and renders. In production:

- prune `data/work/` periodically (it is fully reproducible),
- archive `data/uploads/` on a retention schedule,
- move `data/output/` to object storage.

---

## 5. Running as a service (Linux)

```bash
sudo apt install ffmpeg fonts-noto-cjk
sudo cp scripts/vns.service /etc/systemd/system/
sudo nano /etc/systemd/system/vns.service   # adjust User= and WorkingDirectory
sudo systemctl daemon-reload
sudo systemctl enable --now vns
journalctl -u vns -f
```

### Windows

Register with [NSSM](https://nssm.cc/):

```
nssm install VideoNarratorAI "C:\path\to\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8080"
nssm set VideoNarratorAI AppDirectory "C:\path\to\services\api"
nssm set VideoNarratorAI Start SERVICE_AUTO_START
nssm start VideoNarratorAI
```

---

## 6. Notes for reverse-proxied setups

- Long jobs need a relaxed `proxy_read_timeout` (see the Nginx sample above).
- Video is served with Range requests; the backend answers `206 Partial Content`.
  Do not cache `/api/`.
- The client IP comes from `X-Forwarded-For`; make sure your app honours it.

---

## 7. Upgrading

```bash
git pull
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # Windows
./scripts/start.sh                                             # Linux / macOS
```

Schema changes are applied automatically (SQLAlchemy `create_all`). Back up
`data/station.db` and `data/output/` before upgrading.
