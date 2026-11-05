/**
 * 本机后端的定位、启动与健康检查。
 *
 * 单独成模块（不 import electron），方便在没有图形环境的机器上单独测试。
 */

import { spawn, ChildProcess, spawnSync } from "child_process";
import { existsSync, mkdirSync, appendFileSync } from "fs";
import { homedir } from "os";
import { join, dirname, resolve } from "path";
import http from "http";

export interface BackendTarget {
  command: string;
  args: string[];
  cwd: string;
  /** 来源说明，便于排查 */
  source: "bundled" | "venv" | "system";
}

/** RA-34 F-3：桌面模式的诊断日志（userData/logs/backend.log）。
 * Electron 未初始化时（单元测试）静默跳过。 */
function deskLog(msg: string): void {
  try {
    // electron 的 app 不能在此模块 import（保持可单测）；调用方注入 app 前用兜底路径
    const dir = process.env.VNS_DESKTOP_LOG_DIR;
    if (!dir) return;
    mkdirSync(dir, { recursive: true });
    appendFileSync(join(dir, "backend.log"), `[${new Date().toISOString()}] ${msg}\n`);
  } catch {
    /* 诊断日志失败绝不影响主流程 */
  }
}

/** RA-34 F-3：冻结模式用户数据目录（%APPDATA%/VideoNarrator AI/data）。
 * 仅在打包模式注入 VC_DATA_DIR，数据在卸载重装后保留（NSIS
 * deleteAppDataOnUninstall:false 已验证），且绝不落入安装目录或
 * PyInstaller 临时目录。 */
export function desktopDataDir(appName = "VideoNarrator AI"): string {
  const base =
    process.platform === "win32"
      ? process.env.APPDATA || join(homedir(), "AppData", "Roaming")
      : process.platform === "darwin"
        ? join(homedir(), "Library", "Application Support")
        : process.env.XDG_DATA_HOME || join(homedir(), ".local", "share");
  return join(base, appName, "data");
}

/** 仓库根目录：打包后是 resources/app.asar 的上级，开发态是 apps/desktop 的上级 */
export function repoRoot(appPath: string): string {
  const desktopDir = dirname(appPath);
  const appsDir = dirname(desktopDir);
  return resolve(appsDir, "..");
}

/** 定位可用的后端启动方式。 */
export function resolveBackend(root: string, port: number, resourcesPath?: string): BackendTarget | null {
  const uvicornArgs = [
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    String(port),
  ];

  // 1) 安装包内的独立可执行文件（PyInstaller）
  if (resourcesPath) {
    const bundled = join(resourcesPath, "server", "vns-server");
    const bundledExe = process.platform === "win32" ? `${bundled}.exe` : bundled;
    if (existsSync(bundledExe)) {
      return { command: bundledExe, args: [], cwd: dirname(bundledExe), source: "bundled" };
    }
  }

  const apiDir = join(root, "services", "api");

  // 2) 仓库虚拟环境
  const venvPython =
    process.platform === "win32"
      ? join(root, "services", "api", ".venv", "Scripts", "python.exe")
      : join(root, "services", "api", ".venv", "bin", "python");
  if (existsSync(venvPython)) {
    return { command: venvPython, args: uvicornArgs, cwd: apiDir, source: "venv" };
  }

  // 3) 系统 Python
  const probe = spawnSync(process.platform === "win32" ? "where" : "which", ["python3"], {
    encoding: "utf-8",
  });
  const systemPython = probe.status === 0 ? probe.stdout.split(/\r?\n/)[0]?.trim() : null;
  if (systemPython && existsSync(apiDir)) {
    return { command: systemPython, args: uvicornArgs, cwd: apiDir, source: "system" };
  }
  return null;
}

/** 检测端口是否已被占用。RA-34 F-2：桌面/bundled 模式端口冲突直接失败，
 * 不再静默换端口——换端口对 bundled 后端无效（它只会监听 VNS_PORT），
 * 且静默降级会让健康检查误把占用者的响应当成本应用 Ready。 */
export function isPortFree(port: number): Promise<boolean> {
  return new Promise((res) => {
    const server = http.createServer();
    server.once("error", () => res(false));
    server.listen(port, "127.0.0.1", () => {
      server.close(() => res(true));
    });
  });
}

/**
 * 找可用端口（被占用则交给系统分配）。
 *
 * RA-34 F-2 限定：仅适用于端口通过 argv 传给后端的场景（venv/system 开发模式、
 * 自检脚本）。打包 bundled 模式绝不可用——bundled 后端只监听 VNS_PORT，
 * 该路径由 isPortFree + 明确失败保证就绪判定不被端口占用者污染。
 */
export function findFreePort(preferred: number): Promise<number> {
  return new Promise((resolvePort) => {
    const server = http.createServer();
    server.once("error", () => {
      const s = http.createServer();
      s.once("error", () => resolvePort(preferred));
      s.listen(0, "127.0.0.1", () => {
        const port = (s.address() as { port: number }).port;
        s.close(() => resolvePort(port));
      });
    });
    server.listen(preferred, "127.0.0.1", () => {
      server.close(() => resolvePort(preferred));
    });
  });
}

/**
 * 轮询 /api/health 直到“本后端”就绪。
 * RA-34 F-2：就绪判定必须验证响应体身份（app 字段 + /api/ping），
 * 仅 HTTP 200 不算 Ready——占用端口的其他程序也可能返回 200。
 */
export function waitForHealth(port: number, timeoutMs = 60000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolveHealth, rejectHealth) => {
    const retry = (why: string) => {
      deskLog(`health retry: ${why}`);
      if (Date.now() > deadline) {
        rejectHealth(new Error("本地服务启动超时（端口上未出现 VideoNarrator 后端身份）"));
      } else {
        setTimeout(attempt, 500);
      }
    };
    const attempt = () => {
      const req = http.get(
        { host: "127.0.0.1", port, path: "/api/health", timeout: 2000 },
        (res) => {
          const chunks: Buffer[] = [];
          res.on("data", (c) => chunks.push(c));
          res.on("end", () => {
            if (res.statusCode !== 200) {
              retry(`status ${res.statusCode}`);
              return;
            }
            let body: { app?: unknown };
            try {
              body = JSON.parse(Buffer.concat(chunks).toString("utf-8"));
            } catch {
              retry("health body not JSON");
              return;
            }
            if (body.app !== "VideoNarrator AI") {
              retry(`foreign app identity: ${JSON.stringify(body.app)}`);
              return;
            }
            // 二次确认 /api/ping 同一身份，避免任意 JSON 服务伪装 app 字段
            const ping = http.get(
              { host: "127.0.0.1", port, path: "/api/ping", timeout: 2000 },
              (pr) => {
                const pc: Buffer[] = [];
                pr.on("data", (c) => pc.push(c));
                pr.on("end", () => {
                  try {
                    const pj = JSON.parse(Buffer.concat(pc).toString("utf-8"));
                    if (pr.statusCode === 200 && pj.app === "VideoNarrator AI") {
                      resolveHealth();
                    } else {
                      retry("ping identity mismatch");
                    }
                  } catch {
                    retry("ping body not JSON");
                  }
                });
              },
            );
            ping.on("error", (e) => retry(`ping error: ${e.message}`));
            ping.on("timeout", () => {
              ping.destroy();
              retry("ping timeout");
            });
          });
        },
      );
      req.on("error", (e) => retry(`health error: ${e.message}`));
      req.on("timeout", () => {
        req.destroy();
        retry("health timeout");
      });
    };
    attempt();
  });
}

export interface StartedBackend {
  process: ChildProcess;
  port: number;
  url: string;
  source: BackendTarget["source"];
}

/** 启动后端并等待它就绪。 */
export async function startBackend(
  root: string,
  preferredPort: number,
  resourcesPath?: string,
  log?: (line: string) => void,
): Promise<StartedBackend> {
  const port = preferredPort;

  // RA-34 F-2：桌面模式端口冲突 → 明确失败（附用户可读指引）。
  if (!(await isPortFree(port))) {
    throw new Error(
      `端口 ${port} 已被其他程序占用，VideoNarrator AI 拒绝启动以免误连。` +
        "请关闭占用该端口的程序（常见：开发模式的服务）后重试。",
    );
  }

  const target = resolveBackend(root, port, resourcesPath);
  if (!target) {
    throw new Error(
      "找不到本地后端。请先运行 scripts/setup.ps1 安装依赖，或使用官网提供的安装包。",
    );
  }

  // 为打包后的后端提供确定的 FFmpeg/FFprobe 路径。
  // 资源目录布局：resources/server/{vns-server,ffmpeg,ffprobe}
  let ffmpegPath: string | null = null;
  let ffprobePath: string | null = null;
  let dataDir: string | null = null;
  let frontendDist: string | null = null;
  if (resourcesPath) {
    const serverDir = join(resourcesPath, "server");
    ffmpegPath = join(serverDir, process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg");
    ffprobePath = join(serverDir, process.platform === "win32" ? "ffprobe.exe" : "ffprobe");
  }
  // RA-34 F-2/F-3：仅 bundled（冻结）来源注入端口/数据目录/前端资源。
  // venv/system 开发来源保持原行为（argv 传端口、仓库 data、monorepo 前端），
  // 避免打包判定污染开发环境。
  const isBundledTarget = target.source === "bundled";
  if (isBundledTarget) {
    dataDir = desktopDataDir();
    mkdirSync(dataDir, { recursive: true });
    // RA-34 F-3：冻结模式前端资源必须真实存在。缺失时明确失败——
    // 绝不回退开发目录/开发服务器（用户机器上不存在且可能陈旧）。
    const fe = resourcesPath ? join(resourcesPath, "web", "dist") : null;
    if (!fe || !existsSync(fe)) {
      throw new Error(
        `安装包内前端资源缺失：${fe ?? "(未定位 resourcesPath)"}。` +
          "安装包已损坏或不完整，请重新下载安装。",
      );
    }
    frontendDist = fe;
  }

  deskLog(
    `spawn source=${target.source} port=${port} dataDir=${dataDir ?? "(dev)"} frontend=${frontendDist ?? "(dev)"}`,
  );
  const child = spawn(target.command, target.args, {
    cwd: target.cwd,
    env: {
      ...process.env,
      PYTHONUTF8: "1",
      PYTHONUNBUFFERED: "1",
      ...(ffmpegPath ? { VC_FFMPEG: ffmpegPath } : {}),
      ...(ffprobePath ? { VC_FFPROBE: ffprobePath } : {}),
      ...(isBundledTarget ? { VNS_PORT: String(port) } : {}),
      ...(dataDir ? { VC_DATA_DIR: dataDir } : {}),
      ...(frontendDist ? { VC_FRONTEND_DIST: frontendDist } : {}),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  const capture = (chunk: Buffer) => {
    const text = chunk.toString("utf-8");
    log?.(`[server] ${text}`);
    deskLog(`[server] ${text.trimEnd()}`);
  };
  child.stdout?.on("data", capture);
  child.stderr?.on("data", capture);
  child.on("exit", (code, signal) => deskLog(`backend exit code=${code} signal=${signal}`));

  try {
    await waitForHealth(port);
  } catch (err) {
    child.kill();
    throw err;
  }

  return { process: child, port, url: `http://127.0.0.1:${port}`, source: target.source };
}
