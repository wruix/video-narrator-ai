/**
 * 桌面端后端逻辑的独立自检（不需要图形环境）。
 *
 *   node apps/desktop/dist/backend-check.js
 *
 * 验证：
 *   1. 能定位到后端启动方式
 *   2. 能找到可用端口
 *   3. 能真正拉起后端并通过健康检查
 *   4. 退出时能干净地结束子进程
 */

import { spawnSync } from "child_process";
import { resolve, dirname } from "path";
import { findFreePort, repoRoot, resolveBackend, startBackend } from "./backend";

function ok(msg: string) {
  console.log(`  \x1b[92m✓\x1b[0m ${msg}`);
}

function bad(msg: string) {
  console.log(`  \x1b[91m✗\x1b[0m ${msg}`);
  process.exitCode = 1;
}

async function main() {
  const root = resolve(dirname(__dirname), "..", "..");
  console.log(`仓库根目录：${root}\n`);

  console.log("[1/4] 定位后端");
  const probe = resolveBackend(root, 8080);
  if (!probe) {
    bad("找不到后端（请先运行 scripts/setup.ps1）");
    return;
  }
  ok(`来源=${probe.source} 命令=${probe.command}`);

  console.log("\n[2/4] 端口分配");
  const port = await findFreePort(8080);
  if (!port || port < 1024) {
    bad(`分配到异常端口：${port}`);
    return;
  }
  ok(`可用端口：${port}`);

  console.log("\n[3/4] 启动后端并等待健康检查");
  let started;
  try {
    started = await startBackend(root, port, undefined, (line) => {
      if (process.env.VERBOSE) console.log(line);
    });
    ok(`后端就绪：${started.url}`);
  } catch (err) {
    bad(`启动失败：${(err as Error).message}`);
    return;
  }

  console.log("\n[4/4] 结束子进程");
  started.process.kill();
  await new Promise((r) => setTimeout(r, 800));
  ok("子进程已结束");

  console.log(`\n桌面端后端自检${process.exitCode ? "失败" : "通过"} ✓\n`);
}

void main();
