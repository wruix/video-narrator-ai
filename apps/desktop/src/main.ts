/**
 * Electron 主进程。
 *
 * 职责：
 *  1. 启动本机 Python 后端（优先用打包好的独立可执行文件，其次用仓库虚拟环境）
 *  2. 等后端健康检查通过后打开窗口，指向 http://127.0.0.1:<port>
 *  3. 退出时干净地结束子进程
 *
 * 网页版与桌面端共用同一套前端与后端，只是入口不同。
 */

import { app, BrowserWindow, Menu, dialog, shell } from "electron";
import { repoRoot, startBackend, type StartedBackend } from "./backend";
import { dataDir } from "./paths";

const APP_NAME = "VideoNarrator AI";
const DEFAULT_PORT = 8080;

let mainWindow: BrowserWindow | null = null;
let backend: StartedBackend | null = null;

function createWindow(url: string) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1080,
    minHeight: 700,
    backgroundColor: "#0b0d12",
    title: APP_NAME,
    show: false,
    webPreferences: {
      preload: `${__dirname}/preload.js`,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow?.show());
  mainWindow.loadURL(url);

  // 外部链接交给系统浏览器
  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    void shell.openExternal(target);
    return { action: "deny" };
  });
}

function buildMenu() {
  const isMac = process.platform === "darwin";
  const template: Electron.MenuItemConstructorOptions[] = [
    ...(isMac
      ? [
          {
            label: APP_NAME,
            submenu: [
              { role: "about" as const, label: `About ${APP_NAME}` },
              { type: "separator" as const },
              { role: "hide" as const, label: "Hide" },
              { role: "quit" as const, label: "Quit" },
            ],
          },
        ]
      : []),
    {
      label: "File",
      submenu: [
        {
          label: "Open data folder",
          click: () => {
            void shell.openPath(dataDir);
          },
        },
        { type: "separator" },
        isMac ? { role: "close", label: "Close window" } : { role: "quit", label: "Quit" },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo", label: "Undo" },
        { role: "redo", label: "Redo" },
        { type: "separator" },
        { role: "cut", label: "Cut" },
        { role: "copy", label: "Copy" },
        { role: "paste", label: "Paste" },
        { role: "selectAll", label: "Select all" },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload", label: "Reload" },
        { role: "toggleDevTools", label: "Developer tools" },
        { type: "separator" },
        { role: "resetZoom", label: "Actual size" },
        { role: "zoomIn", label: "Zoom in" },
        { role: "zoomOut", label: "Zoom out" },
        { type: "separator" },
        { role: "togglefullscreen", label: "Fullscreen" },
      ],
    },
    {
      label: "Help",
      submenu: [
        {
          label: "Project homepage",
          click: () => void shell.openExternal("https://github.com/your-org/video-narrator-ai"),
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ---------------------------------------------------------------- 生命周期

// 单实例：第二次启动时聚焦已有窗口
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

app.whenReady().then(async () => {
  buildMenu();
  try {
    const root = repoRoot(app.getAppPath());
    backend = await startBackend(root, DEFAULT_PORT, process.resourcesPath, (line) =>
      console.log(line),
    );
    createWindow(backend.url);
  } catch (err) {
    dialog.showErrorBox(
      `${APP_NAME} failed to start`,
      `${(err as Error).message}\n\nMake sure FFmpeg is installed and that you have run scripts/setup.ps1.`,
    );
    app.quit();
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      void startBackend(repoRoot(app.getAppPath()), DEFAULT_PORT, process.resourcesPath).then(
        (b) => {
          backend = b;
          createWindow(b.url);
        },
      );
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backend?.process && !backend.process.killed) {
    backend.process.kill();
  }
});
