import { useState } from "react";
import { useTranslation } from "@vns/i18n";
import { useStore } from "@/store/useStore";

export default function Sidebar() {
  const { t } = useTranslation();
  const projects = useStore((s) => s.projects);
  const current = useStore((s) => s.current);
  const select = useStore((s) => s.selectProject);
  const create = useStore((s) => s.createProject);
  const remove = useStore((s) => s.deleteProject);
  const toast = useStore((s) => s.toast);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const handleCreate = async () => {
    try {
      await create(name.trim() || t("common.unnamed"));
      setName("");
      setCreating(false);
    } catch (e) {
      toast("error", t("errors.createFailed", { msg: (e as Error).message }));
    }
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <span className="sidebar-title">{t("common.projects")}</span>
        <button className="btn sm ghost" onClick={() => setCreating((v) => !v)}>
          {t("common.new")}
        </button>
      </div>

      {creating && (
        <div style={{ padding: "0 10px 10px" }}>
          <input
            autoFocus
            type="text"
            placeholder={t("common.unnamed")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleCreate();
              if (e.key === "Escape") setCreating(false);
            }}
          />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn sm primary" onClick={() => void handleCreate()}>
              {t("common.save")}
            </button>
            <button className="btn sm ghost" onClick={() => setCreating(false)}>
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}

      <div className="project-list">
        {projects.length === 0 && !creating && (
          <div style={{ padding: "18px 12px", color: "var(--fg-2)", fontSize: 12.5 }}>
            {t("sidebar.empty")}
          </div>
        )}
        {projects.map((p) => (
          <div
            key={p.id}
            className={`project-item ${current?.id === p.id ? "active" : ""}`}
            onClick={() => void select(p.id)}
          >
            <div className="name">{p.name}</div>
            <div className="meta">
              <span className={`tag ${statusTag(p.status)}`}>{t(`sidebar.status.${p.status}`)}</span>
              {p.duration > 0 && <span>{p.duration.toFixed(0)}s</span>}
              <span className="spacer" />
              <span
                style={{ opacity: 0.5 }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm(t("sidebar.deleteConfirm", { name: p.name }))) {
                    void remove(p.id);
                  }
                }}
              >
                ✕
              </span>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

function statusTag(status: string): string {
  switch (status) {
    case "uploaded":
      return "accent";
    case "analyzing":
    case "rendering":
    case "awaiting_review":
      return "warn";
    case "approved":
    case "completed":
      return "ok";
    case "failed":
      return "err";
    default:
      return "";
  }
}
