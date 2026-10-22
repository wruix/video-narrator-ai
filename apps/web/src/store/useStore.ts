import { create } from "zustand";
import { i18n } from "@vns/i18n";
import { api } from "@/lib/api";
import type {
  HealthInfo,
  Job,
  Project,
  ProviderCatalog,
  RenderItem,
  Shot,
} from "@/lib/types";

export interface Toast {
  id: number;
  kind: "info" | "success" | "error";
  text: string;
}

interface AppState {
  health: HealthInfo | null;
  catalog: ProviderCatalog | null;
  projects: Project[];
  current: Project | null;
  shots: Shot[];
  jobs: Job[];
  renders: RenderItem[];
  step: number;
  busy: string | null;
  toasts: Toast[];
  pollTimer: number | null;
  needsToken: boolean;

  bootstrap: () => Promise<void>;
  selectProject: (id: number) => Promise<void>;
  createProject: (name?: string) => Promise<void>;
  deleteProject: (id: number) => Promise<void>;
  uploadVideo: (file: File, onProgress?: (pct: number) => void) => Promise<void>;
  patchProject: (patch: Partial<Project>) => Promise<void>;
  runAnalysis: () => Promise<void>;
  refreshShots: () => Promise<void>;
  updateShot: (shotId: number, patch: Partial<Shot>) => Promise<void>;
  regenerateShot: (shotId: number, instruction?: string) => Promise<void>;
  approve: () => Promise<void>;
  runRender: () => Promise<void>;
  refreshRenders: () => Promise<void>;
  setStep: (step: number) => void;
  setBusy: (label: string | null) => void;
  toast: (kind: Toast["kind"], text: string) => void;
  dismissToast: (id: number) => void;
  poll: () => Promise<void>;
  setNeedsToken: (v: boolean) => void;
}

let toastSeq = 1;

export const useStore = create<AppState>((set, get) => ({
  health: null,
  catalog: null,
  projects: [],
  current: null,
  shots: [],
  jobs: [],
  renders: [],
  step: 0,
  busy: null,
  toasts: [],
  pollTimer: null,
  needsToken: false,

  setNeedsToken(v) {
    set({ needsToken: v });
  },

  async bootstrap() {
    const [health, catalog] = await Promise.allSettled([api.health(), api.providers()]);
    if (health.status === "fulfilled") set({ health: health.value });
    if (catalog.status === "fulfilled") {
      set({ catalog: catalog.value });
    } else if ((catalog.reason as { status?: number })?.status === 401) {
      set({ needsToken: true });
    }
    try {
      const list = await api.listProjects();
      set({ projects: list.items });
      if (list.items.length) await get().selectProject(list.items[0].id);
    } catch (e) {
      if ((e as { status?: number }).status === 401) set({ needsToken: true });
    }
  },

  async selectProject(id) {
    const detail = await api.getProject(id);
    set({ current: detail, shots: detail.shots ?? [], jobs: detail.jobs ?? [], renders: detail.renders ?? [] });
  },

  async createProject(name) {
    const p = await api.createProject(name?.trim() || "未命名项目");
    const list = await api.listProjects();
    set({ projects: list.items });
    await get().selectProject(p.id);
    get().setStep(0);
  },

  async deleteProject(id) {
    await api.deleteProject(id);
    const list = await api.listProjects();
    set({ projects: list.items });
    if (get().current?.id === id) {
      set({ current: null, shots: [], jobs: [], renders: [] });
      if (list.items.length) await get().selectProject(list.items[0].id);
    }
  },

  async uploadVideo(file, onProgress) {
    const current = get().current;
    if (!current) throw new Error("请先创建项目");
    set({ busy: "正在上传视频…" });
    try {
      const res = await api.uploadVideo(current.id, file, onProgress);
      await get().patchProject({});
      get().toast("success", i18n.t("toast.uploadDone", { size: `${(res.size / 1048576).toFixed(1)} MB` }));
      get().setStep(1);
    } catch (e) {
      get().toast("error", i18n.t("errors.uploadFailed", { msg: (e as Error).message }));
      throw e;
    } finally {
      set({ busy: null });
    }
  },

  async patchProject(patch) {
    const current = get().current;
    if (!current) return;
    const updated = await api.updateProject(current.id, patch);
    set({ current: { ...current, ...updated } });
  },

  async runAnalysis() {
    const current = get().current;
    if (!current) return;
    set({ busy: "正在分析视频…" });
    try {
      const job = await api.startAnalysis(current.id);
      set({ jobs: [job, ...get().jobs], step: 2 });
      get().toast("info", i18n.t("toast.analyzeStarted"));
      await get().poll();
    } catch (e) {
      get().toast("error", i18n.t("errors.analyzeFailed", { msg: (e as Error).message }));
    } finally {
      set({ busy: null });
    }
  },

  async refreshShots() {
    const current = get().current;
    if (!current) return;
    const res = await api.listShots(current.id);
    set({ shots: res.items });
  },

  async updateShot(shotId, patch) {
    const current = get().current;
    if (!current) return;
    const updated = await api.updateShot(current.id, shotId, patch);
    set({ shots: get().shots.map((s) => (s.id === updated.id ? updated : s)) });
  },

  async regenerateShot(shotId, instruction = "") {
    const current = get().current;
    if (!current) return;
    set({ busy: "正在重新生成文案…" });
    try {
      const updated = await api.regenerateShot(current.id, shotId, instruction);
      set({ shots: get().shots.map((s) => (s.id === updated.id ? updated : s)) });
      get().toast("success", i18n.t("toast.rewriteDone"));
    } catch (e) {
      get().toast("error", i18n.t("errors.rewriteFailed", { msg: (e as Error).message }));
    } finally {
      set({ busy: null });
    }
  },

  async approve() {
    const current = get().current;
    if (!current) return;
    try {
      await api.approve(current.id);
      await get().patchProject({});
      get().toast("success", i18n.t("toast.approved"));
      get().setStep(3);
    } catch (e) {
      get().toast("error", i18n.t("errors.approveFailed", { msg: (e as Error).message }));
    }
  },

  async runRender() {
    const current = get().current;
    if (!current) return;
    set({ busy: "正在生成成片…" });
    try {
      const job = await api.startRender(current.id);
      set({ jobs: [job, ...get().jobs] });
      get().toast("info", i18n.t("toast.renderStarted"));
      await get().poll();
    } catch (e) {
      get().toast("error", i18n.t("errors.analyzeFailed", { msg: (e as Error).message }));
    } finally {
      set({ busy: null });
    }
  },

  async refreshRenders() {
    const current = get().current;
    if (!current) return;
    const res = await api.listRenders(current.id);
    set({ renders: res.items });
  },

  setStep(step) {
    set({ step });
  },

  setBusy(busy) {
    set({ busy });
  },

  toast(kind, text) {
    const id = toastSeq++;
    set({ toasts: [...get().toasts, { id, kind, text }] });
    window.setTimeout(() => get().dismissToast(id), kind === "error" ? 7000 : 3500);
  },

  dismissToast(id) {
    set({ toasts: get().toasts.filter((t) => t.id !== id) });
  },

  async poll() {
    const current = get().current;
    if (!current) return;
    const jobs = await api.listProjects()
      .then(() => api.getProject(current.id))
      .then((d) => d.jobs ?? [])
      .catch(() => get().jobs);
    if (jobs) set({ jobs });

    const active = (jobs ?? []).find((j) => j.status === "running" || j.status === "queued");
    if (active) {
      if (get().pollTimer) window.clearTimeout(get().pollTimer!);
      const timer = window.setTimeout(() => void get().poll(), 1500);
      set({ pollTimer: timer });
      return;
    }

    // 任务已结束，刷新项目状态
    const detail = await api.getProject(current.id).catch(() => null);
    if (detail) {
      set({ current: detail, shots: detail.shots ?? get().shots });
      if (detail.status === "awaiting_review") {
        await get().refreshShots();
        get().toast("success", i18n.t("toast.analysisDone"));
        set({ step: 2 });
      }
      if (detail.status === "completed") {
        await get().refreshRenders();
        get().toast("success", i18n.t("toast.renderDone"));
        set({ step: 3 });
      }
    }
  },
}));
