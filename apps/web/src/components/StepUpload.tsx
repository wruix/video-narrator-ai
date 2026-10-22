import { useRef, useState } from "react";
import { useTranslation } from "@vns/i18n";
import { useStore } from "@/store/useStore";
import { api } from "@/lib/api";
import { fmtBytes, fmtDuration } from "@vns/ui";

export default function StepUpload() {
  const { t } = useTranslation();
  const current = useStore((s) => s.current);
  const upload = useStore((s) => s.uploadVideo);
  const patchProject = useStore((s) => s.patchProject);
  const setStep = useStore((s) => s.setStep);
  const [over, setOver] = useState(false);
  const [pct, setPct] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  if (!current) return null;

  const handleFile = async (file: File) => {
    try {
      await upload(file, (p) => setPct(p));
    } finally {
      setPct(null);
    }
  };

  const hasVideo = Boolean(current.video_filename);

  return (
    <div>
      <div className="card">
        <h3 className="card-title">{t("upload.title")}</h3>
        <p className="card-desc">{t("upload.desc")}</p>

        {!hasVideo ? (
          <div
            className={`dropzone ${over ? "over" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setOver(false);
              const f = e.dataTransfer.files?.[0];
              if (f) void handleFile(f);
            }}
          >
            <div className="icon">⬆</div>
            <div style={{ fontWeight: 560, marginBottom: 4 }}>{t("upload.dropTitle")}</div>
            <div style={{ color: "var(--fg-2)", fontSize: 12.5 }}>
              {t("upload.dropHint", { size: "4 GB" })}
            </div>
          </div>
        ) : (
          <div className="render-item" style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 22 }}>🎞️</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontWeight: 560,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {current.video_filename}
              </div>
              <div style={{ fontSize: 12, color: "var(--fg-2)" }}>
                {fmtBytes(current.video_size)} · {current.width}×{current.height} ·{" "}
                {fmtDuration(current.duration)} · {current.fps.toFixed(2)} fps ·{" "}
                {current.has_audio ? "audio" : "no audio"}
              </div>
            </div>
            <button className="btn sm" onClick={() => inputRef.current?.click()}>
              {t("upload.replace")}
            </button>
          </div>
        )}

        {pct !== null && (
          <>
            <div className="progress" style={{ marginBottom: 8 }}>
              <div style={{ width: `${pct}%` }} />
            </div>
            <div style={{ fontSize: 12, color: "var(--fg-2)" }}>
              {t("upload.uploading", { pct })}
            </div>
          </>
        )}

        <input
          ref={inputRef}
          type="file"
          accept="video/*"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleFile(f);
            e.target.value = "";
          }}
        />

        {hasVideo && (
          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn primary" onClick={() => setStep(1)}>
              {t("upload.next")}
            </button>
          </div>
        )}
      </div>

      {hasVideo && (
        <div className="card">
          <h3 className="card-title">{t("upload.previewTitle")}</h3>
          <div className="video-frame">
            <video src={api.videoUrl(current.id)} controls preload="metadata" />
          </div>
        </div>
      )}

      <div className="card">
        <h3 className="card-title">{t("upload.notesTitle")}</h3>
        <p className="card-desc">{t("upload.notesDesc")}</p>
        <textarea
          placeholder={t("upload.notesPlaceholder")}
          value={current.user_notes}
          onChange={(e) => void patchProject({ user_notes: e.target.value })}
          style={{ minHeight: 88 }}
        />
      </div>
    </div>
  );
}
