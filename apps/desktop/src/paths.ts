/**
 * 数据目录定位（供菜单「打开数据目录」使用）。
 */
import { join, resolve } from "path";
import { app } from "electron";

export function repoRoot(): string {
  const desktopDir = resolve(app.getAppPath(), "..");
  return resolve(desktopDir, "..");
}

export const dataDir = process.env.VC_DATA_DIR || join(repoRoot(), "data");
