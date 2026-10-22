/**
 * 本机后端的定位、启动与健康检查。
 *
 * 单独成模块（不 import electron），方便在没有图形环境的机器上单独测试。
 */

import { spawn, ChildProcess, spawnSync } from "child_process";
import { existsSync } from "fs";
import { join, dirname, resolve } from "path";
import http from "http";

export interface BackendTarget {
  command: string;
  args: string[];
  cwd: string;
  /** 来源说明，便于排查 */
  source: "bundled" | "venv" | "system";
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

/** 找一个可用端口；被占用时交给系统分配。 */
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

/** 轮询 /api/health 直到服务就绪。 */
export function waitForHealth(port: number, timeoutMs = 60000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolveHealth, rejectHealth) => {
    const retry = () => {
      if (Date.now() > deadline) {
        rejectHealth(new Error("本地服务启动超时"));
      } else {
        setTimeout(attempt, 500);
      }
    };
    const attempt = () => {
      const req = http.get(
        { host: "127.0.0.1", port, path: "/api/health", timeout: 2000 },
        (res) => {
          res.resume();
          if (res.statusCode === 200) resolveHealth();
          else retry();
        },
      );
      req.on("error", retry);
      req.on("timeout", () => {
        req.destroy();
        retry();
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
  const port = await findFreePort(preferredPort);
  const target = resolveBackend(root, port, resourcesPath);
  if (!target) {
    throw new Error(
      "找不到本地后端。请先运行 scripts/setup.ps1 安装依赖，或使用官网提供的安装包。",
    );
  }

  const child = spawn(target.command, target.args, {
    cwd: target.cwd,
    env: { ...process.env, PYTHONUTF8: "1", PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });

  const capture = (chunk: Buffer) => {
    const text = chunk.toString("utf-8");
    log?.(`[server] ${text}`);
  };
  child.stdout?.on("data", capture);
  child.stderr?.on("data", capture);

  try {
    await waitForHealth(port);
  } catch (err) {
    child.kill();
    throw err;
  }

  return { process: child, port, url: `http://127.0.0.1:${port}`, source: target.source };
}
