import type {
  HealthInfo,
  Job,
  KeyInfo,
  Project,
  ProviderCatalog,
  RenderItem,
  Shot,
  UsageSummary,
} from "./types";

const BASE = "/api";
const TOKEN_KEY = "vns_access_token";

/** 访问口令（服务端设置了 VC_ACCESS_TOKEN 时需要） */
export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 忽略隐私模式等异常 */
  }
}

/** 给直链（video 标签 / 下载链接）追加凭证 */
function withToken(url: string): string {
  const token = getToken();
  if (!token) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("X-Access-Token", token);

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    throw new ApiError("需要访问口令：请在「设置与密钥」中填写", 401);
  }
  if (!res.ok) {
    let detail = `请求失败（${res.status}）`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
      else if (Array.isArray(data?.detail)) detail = data.detail.map((d: any) => d.msg).join("；");
    } catch {
      /* 忽略解析失败 */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthInfo>("/health"),
  providers: () => request<ProviderCatalog>("/providers"),

  listProjects: () => request<{ items: Project[] }>("/projects"),
  createProject: (name: string) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify({ name }) }),
  getProject: (id: number) => request<Project>(`/projects/${id}`),
  updateProject: (id: number, patch: Partial<Project>) =>
    request<Project>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteProject: (id: number) => request<{ ok: boolean }>(`/projects/${id}`, { method: "DELETE" }),

  uploadVideo: async (id: number, file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData();
    form.append("file", file);
    // 使用 XHR 以便上报上传进度
    return new Promise<{ ok: boolean; size: number; project: Project }>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}/projects/${id}/video`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else {
          let detail = `上传失败（${xhr.status}）`;
          try {
            const d = JSON.parse(xhr.responseText);
            if (typeof d?.detail === "string") detail = d.detail;
          } catch {
            /* noop */
          }
          reject(new ApiError(detail, xhr.status));
        }
      };
      xhr.onerror = () => reject(new ApiError("网络错误，上传失败", 0));
      xhr.send(form);
    });
  },

  startAnalysis: (id: number) => request<Job>(`/projects/${id}/analyze`, { method: "POST" }),
  approve: (id: number) => request<{ ok: boolean; shots: number; empty: number }>(`/projects/${id}/approve`, { method: "POST" }),
  startRender: (id: number) => request<Job>(`/projects/${id}/render`, { method: "POST" }),
  listJobs: (id: number) => request<{ items: Job[] }>(`/projects/${id}/jobs`),

  listShots: (id: number) => request<{ items: Shot[] }>(`/projects/${id}/shots`),
  updateShot: (id: number, shotId: number, patch: Partial<Shot>) =>
    request<Shot>(`/projects/${id}/shots/${shotId}`, { method: "PATCH", body: JSON.stringify(patch) }),
  regenerateShot: (id: number, shotId: number, instruction = "") =>
    request<Shot>(`/projects/${id}/shots/${shotId}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),

  listRenders: (id: number) => request<{ items: RenderItem[] }>(`/projects/${id}/renders`),

  listKeys: () => request<{ keys: KeyInfo[]; prefer: string }>("/settings/keys"),
  setKey: (provider: string, key: string, scope: "user" | "server") =>
    request<{ ok: boolean }>("/settings/keys", {
      method: "POST",
      body: JSON.stringify({ provider, key, scope }),
    }),
  deleteKey: (provider: string, scope: "user" | "server") =>
    request<{ ok: boolean }>(`/settings/keys/${provider}?scope=${scope}`, { method: "DELETE" }),
  setPreference: (prefer: "user" | "server") =>
    request<{ ok: boolean }>("/settings/preferences", {
      method: "POST",
      body: JSON.stringify({ prefer }),
    }),
  testConnection: (provider: string, kind: "vision" | "text" | "tts") =>
    request<{ ok: boolean; message: string; source?: string }>("/settings/test", {
      method: "POST",
      body: JSON.stringify({ provider, kind }),
    }),

  usage: () => request<UsageSummary>("/usage"),

  videoUrl: (id: number) => withToken(`${BASE}/projects/${id}/video`),
  frameUrl: (id: number, frame: string) => withToken(`${BASE}/projects/${id}/frames/${encodeURIComponent(frame)}`),
  shotAudioUrl: (id: number, shotId: number) => withToken(`${BASE}/projects/${id}/shots/${shotId}/audio`),
  renderPreviewUrl: (id: number, renderId: number) =>
    withToken(`${BASE}/projects/${id}/renders/${renderId}/preview`),
  renderDownloadUrl: (id: number, renderId: number) =>
    withToken(`${BASE}/projects/${id}/renders/${renderId}/download`),
  subtitleUrl: (id: number, renderId: number) =>
    withToken(`${BASE}/projects/${id}/renders/${renderId}/subtitle`),
};
