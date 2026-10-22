/**
 * 预加载脚本：只暴露最小能力，页面拿不到 Node API。
 */
import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("vns", {
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
  },
  /** 桌面端外壳版本，便于界面显示 */
  isDesktop: true,
});
