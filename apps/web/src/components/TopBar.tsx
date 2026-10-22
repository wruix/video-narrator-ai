import { useTranslation, SUPPORTED_LOCALES, setLocale, getLocale } from "@vns/i18n";
import { useStore } from "@/store/useStore";

export default function TopBar({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { t } = useTranslation();
  const health = useStore((s) => s.health);
  const current = useStore((s) => s.current);

  const ffmpegOk = Boolean(health?.ffmpeg && health?.ffprobe);
  const status = !health ? t("app.loading") : ffmpegOk ? t("app.ready") : t("app.ffmpegMissing");

  const onLocale = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setLocale(e.target.value as (typeof SUPPORTED_LOCALES)[number]["id"]);
  };

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">解</span>
        <span>
          {t("app.name")}
          <br />
          <small>{t("app.tagline")}</small>
        </span>
      </div>
      <div className="topbar-spacer" />
      {current && (
        <span className="tag accent" title={current.video_filename ?? ""}>
          {current.name}
        </span>
      )}
      <span className={`tag ${ffmpegOk ? "ok" : "err"}`} title={health?.ffmpeg ?? ""}>
        {status}
      </span>
      <select
        className="locale-switch"
        value={getLocale()}
        onChange={onLocale}
        aria-label={t("common.language")}
        title={t("common.language")}
      >
        {SUPPORTED_LOCALES.map((l) => (
          <option key={l.id} value={l.id}>
            {l.label}
          </option>
        ))}
      </select>
      <button className="btn" onClick={onOpenSettings}>
        ⚙ {t("app.settings")}
      </button>
    </header>
  );
}
