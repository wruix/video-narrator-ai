/**
 * 数据目录定位（供菜单「打开数据目录」使用）。
 *
 * RA-34 F-3：与 backend.ts 的注入规则保持一致 ——
 * 打包模式 = VC_DATA_DIR 注入值（缺省 %APPDATA%/VideoNarrator AI/data），
 * 开发模式 = 仓库 data/。
 */
import { join, resolve } from "path";
import { app } from "electron";
import { desktopDataDir } from "./backend";

export function repoRoot(): string {
  const desktopDir = resolve(app.getAppPath(), "..");
  return resolve(desktopDir, "..");
}

export const dataDir =
  process.env.VC_DATA_DIR ||
  (app.isPackaged ? desktopDataDir() : join(repoRoot(), "data"));
