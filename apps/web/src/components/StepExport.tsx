import { useEffect, useRef, useState } from "react";
import { useTranslation } from "@vns/i18n";
import { useStore } from "@/store/useStore";
import { api } from "@/lib/api";
import { fmtBytes, fmtDuration } from "@vns/ui";
import type { RenderItem } from "@/lib/types";

export default function StepExport() {
  const { t, i18n } = useTranslation();
  const current = useStore((s) => s.current);
  const shots = useStore((s) => s.shots);
  const catalog = useStore((s) => s.catalog);
  const jobs = useStore((s) => s.jobs);
  const renders = useStore((s) => s.renders);
  const runRender = useStore((s) => s.runRender);
  const refreshRenders = useStore((s) => s.refreshRenders);
  const busy = useStore((s) => s.busy);
  const [preview, setPreview] = useState<RenderItem | null>(null);
  const previewRef = useRef<HTMLVideoElement>(null);
  const locale = i18n.language ?? "zh-CN";

  const activeJob = jobs.find((j) => j.status === "running" && j.kind === "render");

  useEffect(() => {
    if (!activeJob) void refreshRenders();
  }, [activeJob?.id, refreshRenders]);

  if (!current) return null;

  const providerName = (id: string, fallback: string) => {
    const key = `providers.${id}`;
    const translated = t(key);
    return translated === key ? fallback : translated;
  };
  const localized = (item: { name?: string; name_en?: string } | undefined, fallback = "") =>
    !item ? fallback : locale.startsWith("zh") ? (item.name ?? fallback) : (item.name_en ?? item.name ?? fallback);

  const ttsProvider = catalog?.tts.find((p) => p.id === current.tts_provider);
  const voice = catalog?.voices.find((v) => v.id === current.voice_id);
  const style = catalog?.styles.find((s) => s.id === current.style);
  const aspect = catalog?.aspects.find((a) => a.id === current.aspect);
  const withNarration = shots.filter((s) => s.narration?.trim()).length;
  const totalChars = shots.reduce((n, s) => n + (s.narration ?? "").trim().length, 0);

  return (
    <div>
      <div className="card">
        <h3 className="card-title">{t("export.title")}</h3>
        <p className="card-desc">
          {t("export.desc", { count: withNarration })}
        </p>

        <div className="kv-list" style={{ marginBottom: 16 }}>
          <div className="kv">
            <span className="k">{t("export.source")}</span>
            <span>
              {current.video_filename}（{fmtDuration(current.duration)}）
            </span>
          </div>
          <div className="kv">
            <span className="k">{t("export.output")}</span>
            <span>
              {localized(aspect, current.aspect)} · {current.width}×{current.height} →{" "}
              {current.aspect === "original" ? t("export.keepRatio") : t("export.cropRatio")}
            </span>
          </div>
          <div className="kv">
            <span className="k">{t("export.style")}</span>
            <span>{localized(style, current.style)}</span>
          </div>
          <div className="kv">
            <span className="k">{t("export.voice")}</span>
            <span>
              {providerName(current.tts_provider, ttsProvider?.name ?? "")} ·{" "}
              {voice?.name ?? current.voice_id} · {current.voice_speed}
            </span>
          </div>
          <div className="kv">
            <span className="k">{t("export.subtitle")}</span>
            <span>
              {current.subtitle_enabled ? t("export.genSrt") : t("export.noSrt")} ·{" "}
              {current.burn_subtitles ? t("export.burnIn") : t("export.externalOnly")}
            </span>
          </div>
          <div className="kv">
            <span className="k">{t("export.scriptScale")}</span>
            <span>
              {t("export.shotsWithText", {
                with: withNarration,
                total: shots.length,
                chars: totalChars,
              })}
            </span>
          </div>
        </div>

        <div className="row">
          <button
            className="btn primary"
            disabled={!shots.length || Boolean(activeJob) || Boolean(busy)}
            onClick={() => void runRender()}
          >
            {activeJob ? t("export.generating") : t("export.generate")}
          </button>
          <span className="spacer" />
          <span style={{ fontSize: 12, color: "var(--fg-2)" }}>{t("export.eta")}</span>
        </div>

        {activeJob && (
          <div style={{ marginTop: 16 }}>
            <div className="row" style={{ marginBottom: 8 }}>
              <strong>{activeJob.detail || t("export.generating")}</strong>
              <span className="tag accent">{Math.round(activeJob.progress * 100)}%</span>
            </div>
            <div className="progress">
              <div style={{ width: `${Math.max(3, activeJob.progress * 100)}%` }} />
            </div>
            <div style={{ fontSize: 12, color: "var(--fg-2)", marginTop: 6 }}>
              {activeJob.message}
            </div>
          </div>
        )}

        {current.error && (
          <div className="banner err" style={{ marginTop: 14, marginBottom: 0 }}>
            {current.error}
          </div>
        )}
      </div>

      {preview && (
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <h3 className="card-title" style={{ margin: 0 }}>
              #{preview.id}
            </h3>
            <span className="spacer" />
            <button className="btn sm" onClick={() => setPreview(null)}>
              {t("common.close")}
            </button>
          </div>
          <div className="video-frame">
            <video
              ref={previewRef}
              src={api.renderPreviewUrl(current.id, preview.id)}
              controls
              preload="metadata"
            />
          </div>
        </div>
      )}

      <div className="card">
        <h3 className="card-title">{t("export.history")}</h3>
        <p className="card-desc">{t("export.historyDesc")}</p>
        {renders.length === 0 ? (
          <div className="empty" style={{ padding: "30px 20px" }}>
            <div className="big">🎞️</div>
            <p>{t("export.noRenders")}</p>
          </div>
        ) : (
          <div className="renders-list">
            {renders.map((r) => (
              <div key={r.id} className="render-item">
                <div style={{ fontSize: 20 }}>🎬</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 560 }}>#{r.id}</div>
                  <div style={{ fontSize: 12, color: "var(--fg-2)" }}>
                    {fmtDuration(r.duration)} · {fmtBytes(r.size)} ·{" "}
                    {r.created_at ? new Date(r.created_at).toLocaleString(locale) : ""}
                    {r.has_subtitle ? " · SRT" : ""}
                  </div>
                </div>
                <button className="btn sm" onClick={() => setPreview(r)}>
                  {t("export.previewBtn")}
                </button>
                <a
                  className="btn sm"
                  href={api.renderDownloadUrl(current.id, r.id)}
                  download
                  style={{ textDecoration: "none" }}
                >
                  {t("export.download")}
                </a>
                {r.has_subtitle && (
                  <a
                    className="btn sm ghost"
                    href={api.subtitleUrl(current.id, r.id)}
                    download
                    style={{ textDecoration: "none" }}
                  >
                    {t("export.srt")}
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="card-title">{t("export.backToEdit")}</h3>
        <p className="card-desc">{t("export.backDesc")}</p>
        <button className="btn" onClick={() => useStore.getState().setStep(2)}>
          {t("export.backToEdit")}
        </button>
      </div>
    </div>
  );
}
