import { useEffect, useRef, useState } from "react";
import { useTranslation } from "@vns/i18n";
import { useStore } from "@/store/useStore";
import { api } from "@/lib/api";
import { fmtTime, estimateSpeechSeconds } from "@vns/ui";

export default function StepReview() {
  const { t, i18n } = useTranslation();
  const current = useStore((s) => s.current);
  const shots = useStore((s) => s.shots);
  const catalog = useStore((s) => s.catalog);
  const updateShot = useStore((s) => s.updateShot);
  const regenerateShot = useStore((s) => s.regenerateShot);
  const approve = useStore((s) => s.approve);
  const jobs = useStore((s) => s.jobs);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [activeShot, setActiveShot] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const saveTimer = useRef<number | null>(null);
  const locale = i18n.language ?? "zh-CN";

  const activeJob = jobs.find((j) => j.status === "running");

  useEffect(() => {
    if (!current) return;
    const t = window.setInterval(() => {
      const el = videoRef.current;
      if (!el) return;
      const inShot = shots.find((s) => el.currentTime >= s.start && el.currentTime < s.end);
      if (inShot) setActiveShot(inShot.id);
    }, 300);
    return () => window.clearInterval(t);
  }, [current, shots]);

  if (!current) return null;

  const value = (id: number, fallback: string) => drafts[id] ?? fallback;

  const onEdit = (id: number, text: string) => {
    setDrafts((d) => ({ ...d, [id]: text }));
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      void updateShot(id, { narration: text });
    }, 600);
  };

  const emptyShots = shots.filter((s) => !value(s.id, s.narration).trim());
  const totalChars = shots.reduce((n, s) => n + value(s.id, s.narration).trim().length, 0);
  const estimated = estimateSpeechSeconds(totalChars);
  const ratio = current.duration > 0 ? estimated / current.duration : 0;
  const emotions = locale.startsWith("zh")
    ? (catalog?.emotions ?? ["default"])
    : (catalog?.emotions_en ?? catalog?.emotions ?? ["default"]);

  const seekTo = (time: number) => {
    const el = videoRef.current;
    if (el) {
      el.currentTime = time;
      void el.play();
    }
  };

  return (
    <div>
      {activeJob && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row">
            <div style={{ flex: 1 }}>
              <div className="row" style={{ marginBottom: 8 }}>
                <strong>{activeJob.detail || t("review.waiting")}</strong>
                <span className="tag accent">{Math.round(activeJob.progress * 100)}%</span>
              </div>
              <div className="progress">
                <div style={{ width: `${Math.max(3, activeJob.progress * 100)}%` }} />
              </div>
              <div style={{ fontSize: 12, color: "var(--fg-2)", marginTop: 6 }}>
                {activeJob.message}
              </div>
            </div>
          </div>
        </div>
      )}

      {shots.length === 0 && !activeJob && (
        <div className="card">
          <div className="empty">
            <div className="big">✍️</div>
            <h3>{t("review.noShots")}</h3>
            <p>{t("review.noShotsHint")}</p>
          </div>
        </div>
      )}

      {shots.length > 0 && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <h3 className="card-title">{t("review.autoCheck")}</h3>
            <div className="stat-grid">
              <div className="stat">
                <div className="k">{t("review.shots")}</div>
                <div className="v">{shots.length}</div>
              </div>
              <div className="stat">
                <div className="k">{t("review.emptyShots")}</div>
                <div className="v" style={{ color: emptyShots.length ? "var(--danger)" : "var(--accent-2)" }}>
                  {emptyShots.length}
                </div>
              </div>
              <div className="stat">
                <div className="k">{t("review.totalChars")}</div>
                <div className="v">{totalChars}</div>
              </div>
              <div className="stat">
                <div className="k">{t("review.estimated")}</div>
                <div className="v">{estimated.toFixed(0)}s</div>
              </div>
              <div className="stat">
                <div className="k">{t("review.videoDuration")}</div>
                <div className="v">{fmtTime(current.duration)}</div>
              </div>
            </div>
            {ratio > 1.05 && (
              <div className="banner warn" style={{ marginTop: 12, marginBottom: 0 }}>
                {t("review.tooLong", { pct: Math.round(ratio * 100) })}
              </div>
            )}
            {emptyShots.length > 0 && (
              <div className="banner warn" style={{ marginTop: 12, marginBottom: 0 }}>
                {t("review.emptyWarn", { count: emptyShots.length })}
              </div>
            )}
          </div>

          <div className="workbench">
            <div className="video-pane">
              <div className="card">
                <h3 className="card-title">{t("review.preview")}</h3>
                <p className="card-desc">{t("review.previewDesc")}</p>
                <div className="video-frame">
                  <video
                    ref={videoRef}
                    src={api.videoUrl(current.id)}
                    controls
                    preload="metadata"
                    onTimeUpdate={(e) => {
                      const el = e.currentTarget;
                      const hit = shots.find((s) => el.currentTime >= s.start && el.currentTime < s.end);
                      if (hit) setActiveShot(hit.id);
                    }}
                  />
                </div>
                <div className="row" style={{ marginTop: 12 }}>
                  <button
                    className="btn sm"
                    onClick={() => {
                      const el = videoRef.current;
                      if (el) el.currentTime = 0;
                    }}
                  >
                    {t("upload.backToStart")}
                  </button>
                  <button
                    className="btn sm"
                    onClick={() => {
                      const el = videoRef.current;
                      if (el) el.pause();
                    }}
                  >
                    {t("upload.pause")}
                  </button>
                  <span className="spacer" />
                  <span className="tag">
                    {current.width}×{current.height}
                  </span>
                  <span className="tag">{current.aspect}</span>
                </div>
              </div>
            </div>

            <div className="shot-list">
              {shots.map((s) => (
                <div key={s.id} className={`shot-card ${activeShot === s.id ? "active" : ""}`}>
                  <div className="shot-head" onClick={() => { setActiveShot(s.id); seekTo(s.start); }}>
                    <span className="shot-no">{s.index + 1}</span>
                    <span className="shot-time">
                      {fmtTime(s.start)} → {fmtTime(s.end)}
                    </span>
                    <span className="tag">{s.duration.toFixed(1)}s</span>
                    <span className="spacer" />
                    {s.locked && <span className="tag warn">{t("review.locked")}</span>}
                  </div>

                  <div className="shot-body">
                    {s.visual && <div className="shot-visual">{s.visual}</div>}

                    {s.frames.length > 0 && (
                      <div className="shot-frames">
                        {s.frames.slice(0, 6).map((f) => (
                          <img
                            key={f}
                            src={api.frameUrl(current.id, f)}
                            alt="keyframe"
                            title={t("review.previewDesc")}
                            onClick={() => seekTo(s.start)}
                          />
                        ))}
                      </div>
                    )}

                    <textarea
                      className="shot-textarea"
                      placeholder={t("review.narrationPlaceholder")}
                      value={value(s.id, s.narration)}
                      onChange={(e) => onEdit(s.id, e.target.value)}
                    />
                    <div className="char-count">
                      {value(s.id, s.narration).trim().length} {t("common.chars")}
                    </div>

                    <div className="inline-controls">
                      <select
                        value={s.emotion}
                        onChange={(e) => void updateShot(s.id, { emotion: e.target.value })}
                      >
                        {emotions.map((em) => (
                          <option key={em} value={em}>
                            {t("review.emotionLabel", { value: em })}
                          </option>
                        ))}
                      </select>
                      <select
                        value={s.speed}
                        onChange={(e) => void updateShot(s.id, { speed: e.target.value })}
                      >
                        {["-20%", "-10%", "+0%", "+10%", "+20%", "+30%"].map((sp) => (
                          <option key={sp} value={sp}>
                            {t("review.speedLabel", { value: sp })}
                          </option>
                        ))}
                      </select>
                      <span className="spacer" />
                      <button
                        className="btn sm"
                        onClick={() => void regenerateShot(s.id)}
                        title={t("review.rewrite")}
                      >
                        {t("review.rewrite")}
                      </button>
                      <button
                        className="btn sm"
                        onClick={() => void updateShot(s.id, { locked: !s.locked })}
                        title={s.locked ? t("review.unlock") : t("review.lock")}
                      >
                        {s.locked ? t("review.unlock") : t("review.lock")}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <div className="row">
              <div>
                <h3 className="card-title" style={{ marginBottom: 2 }}>
                  {t("review.approve")}
                </h3>
                <p className="card-desc" style={{ margin: 0 }}>
                  {t("review.approveDesc")}
                </p>
              </div>
              <span className="spacer" />
              <button className="btn primary" onClick={() => void approve()}>
                {t("review.approve")}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
