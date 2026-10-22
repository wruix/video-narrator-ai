# 部署指南 / Deployment Guide

[English](../en/deployment.md) · [简体中文](../zh-CN/deployment.md)

---

## 一、两种形态 / Two shapes

| | 桌面版 Desktop | 网页版 Web |
| --- | --- | --- |
| 视频处理位置 | 你的机器 | 服务器 |
| 视频是否离开本机 | 否 | 是（上传到服务器） |
| 模型 Key | 用户自己的（BYOK） | 用户自带或平台托管 |
| 安装要求 | 安装包 + FFmpeg | 浏览器 |
| 适合 | 个人、素材敏感、批量 | 团队、协作、免安装 |

两者共用同一套前端与后端代码，只是入口与部署方式不同。

---

## 二、桌面版 / Desktop

### 从 Release 安装

| 平台 | 安装包 |
| --- | --- |
| Windows x64 | `VideoNarrator AI-<version>-x64.exe`（NSIS 安装程序）/ portable 版 |
| macOS | `VideoNarrator AI-<version>-{x64,arm64}.dmg` |
| Linux x64 | `VideoNarrator AI-<version>-x64.AppImage` / `.deb` |

安装包内已包含独立的后端可执行文件，**不需要另外装 Python**；但**需要系统里有 FFmpeg**
（Windows 安装程序会提示检查）。

### 从源码运行

```bash
npm install
npm run build:web
npm run build:desktop
cd apps/desktop && npm start
```

桌面端按以下顺序寻找后端：

1. 安装包内的 `resources/server/vns-server`
2. 仓库虚拟环境 `services/api/.venv`
3. 系统 `python3`（需已装好依赖）

---

## 三、网页版 / Web server

### Docker（推荐）

```bash
cp config/tiers.example.yaml config/tiers.yaml
cp deploy/docker-compose.yml .
export VC_ACCESS_TOKEN="$(openssl rand -hex 24)"
docker compose up -d
```

数据持久化在 `vns-data` 卷（容器内 `/data`）。

### 直接跑

```bash
./scripts/start.sh 0.0.0.0 8080        # Linux / macOS
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Port 8080   # Windows
```

---

## 四、公网部署检查清单 / Public deployment checklist

部署到任何**不止你自己**能访问的地址之前，逐项确认：

### 1. 访问口令（必做）

```ini
VC_ACCESS_TOKEN=<一段足够长的随机字符串>
```

不设置的话，任何人都能调用你的接口、用你的模型 Key 烧钱、把你的素材传上去。
前端会自动弹出「需要访问口令」框；也可以用 `Authorization: Bearer <token>` 头，
或给媒体直链加 `?token=`。

### 2. HTTPS（必做）

视频上传与成片下载走明文 HTTP 会泄露素材。前面挂 Nginx / Caddy / 宝塔面板：

```nginx
server {
    listen 443 ssl http2;
    server_name narration.example.com;

    # 大文件上传
    client_max_body_size 4096m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;      # 渲染任务可能很久
        proxy_send_timeout 3600s;
    }
}
```

### 3. 收紧 CORS

```ini
VC_CORS_ORIGINS=https://narration.example.com
```

### 4. 密钥策略

| 场景 | 做法 |
| --- | --- |
| 自用 / 小团队 | 模式 A：每个用户填自己的 Key（费用各自承担） |
| 对外提供服务 | 模式 B：在设置里把 Key 存为「平台托管」，或用 `VC_SERVER_KEY_*` 环境变量 |

平台托管模式下请配合限流与配额，避免单个任务打爆额度。

### 5. 资源与存储

| 项 | 建议 |
| --- | --- |
| CPU | 4 核以上（视频编码是 CPU 密集型） |
| 内存 | 4 GB 起，处理 4K 建议 8 GB |
| 磁盘 | `VC_DATA_DIR` 按成片体积预留；`work/` 可定期清理 |
| 带宽 | 上传是瓶颈；成片建议转存对象存储 |

### 6. 清理策略

`data/` 下会累积上传素材、关键帧、配音与成片。生产环境建议：

- 定期清理 `data/work/`（可重建）
- `data/uploads/` 按保留期归档
- `data/output/` 迁到对象存储

---

## 五、Linux 常驻运行 / systemd

```bash
sudo apt install ffmpeg fonts-noto-cjk
sudo cp scripts/vns.service /etc/systemd/system/
sudo nano /etc/systemd/system/vns.service   # 改 User= 与 WorkingDirectory
sudo systemctl daemon-reload
sudo systemctl enable --now vns
journalctl -u vns -f
```

---

## 六、Windows 常驻运行

用 [NSSM](https://nssm.cc/) 注册为系统服务：

```
nssm install VideoNarratorAI "C:\path\to\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8080"
nssm set VideoNarratorAI AppDirectory "C:\path\to\services\api"
nssm set VideoNarratorAI Start SERVICE_AUTO_START
nssm start VideoNarratorAI
```

---

## 七、反向代理下的注意事项

- 长任务要放宽 `proxy_read_timeout`（见上面的 Nginx 示例）。
- 视频走 Range 请求，后端已支持 `206 Partial Content`，代理不要缓存 `/api/`。
- 客户端 IP 用于日志，请确认应用读取 `X-Forwarded-For`。

---

## 八、升级 / Upgrading

```bash
git pull
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # Windows
./scripts/start.sh                                             # Linux / macOS
```

数据库迁移是自动的（SQLAlchemy `create_all`）。升级前建议备份 `data/station.db`
与 `data/output/`。
