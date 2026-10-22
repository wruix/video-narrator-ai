# VideoNarrator AI · 桌面端

Windows / macOS / Linux 桌面外壳。内部启动本机 Python 后端，界面与网页版完全一致。

## 开发运行

```bash
# 仓库根目录
npm install
npm run build:web          # 构建共享前端
npm run build:desktop     # 编译 Electron 主进程

cd apps/desktop
npm start
```

桌面端会自动找到以下后端（按优先级）：

1. 安装包内的独立可执行文件 `resources/server/vns-server`
2. 仓库虚拟环境 `services/api/.venv`
3. 系统 `python3`（需已安装 `uvicorn` 与项目依赖）

## 打包

```bash
npm run dist:win
npm run dist:mac
npm run dist:linux
```

产物在 `apps/desktop/release/`。

`electron-builder.yml` 里预留了 `extraResources: ../api/dist/server`，
CI 会先用 PyInstaller 把 Python 后端打成单文件可执行程序再塞进安装包，
这样终端用户不需要自己装 Python。

## 安全边界

- `contextIsolation: true`、`nodeIntegration: false`
- 页面只能通过 `window.vns` 拿到少量只读信息
- 外部链接交给系统浏览器打开
