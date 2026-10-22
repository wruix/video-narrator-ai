export function fmtTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return "00:00";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function fmtTimePrecise(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return "00:00.0";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${s.toFixed(1).padStart(4, "0")}`;
}

export function fmtBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function fmtDuration(seconds: number): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m} 分 ${s} 秒` : `${s} 秒`;
}

export const STATUS_LABEL: Record<string, string> = {
  created: "待上传",
  uploaded: "已就绪",
  analyzing: "分析中",
  awaiting_review: "待审核",
  approved: "已审核",
  rendering: "生成中",
  completed: "已完成",
  failed: "失败",
};

export const STATUS_TAG: Record<string, string> = {
  created: "",
  uploaded: "accent",
  analyzing: "warn",
  awaiting_review: "warn",
  approved: "ok",
  rendering: "warn",
  completed: "ok",
  failed: "err",
};
