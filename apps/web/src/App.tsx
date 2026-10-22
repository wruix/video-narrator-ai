import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "@vns/i18n";
import { useStore } from "@/store/useStore";
import TopBar from "@/components/TopBar";
import Sidebar from "@/components/Sidebar";
import StepUpload from "@/components/StepUpload";
import StepSettings from "@/components/StepSettings";
import StepReview from "@/components/StepReview";
import StepExport from "@/components/StepExport";
import SettingsModal from "@/components/SettingsModal";
import Toasts from "@/components/Toasts";

export default function App() {
  const { t } = useTranslation();
  const step = useStore((s) => s.step);
  const setStep = useStore((s) => s.setStep);
  const bootstrap = useStore((s) => s.bootstrap);
  const busy = useStore((s) => s.busy);
  const current = useStore((s) => s.current);
  const needsToken = useStore((s) => s.needsToken);
  const [showSettings, setShowSettings] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"models" | "tts" | "usage" | "system">("models");

  const STEPS = [
    t("nav.step1"),
    t("nav.step2"),
    t("nav.step3"),
    t("nav.step4"),
  ];

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    if (needsToken) {
      setSettingsTab("system");
      setShowSettings(true);
    }
  }, [needsToken]);

  const openSettings = (tab: "models" | "tts" | "usage" | "system" = "models") => {
    setSettingsTab(tab);
    setShowSettings(true);
  };

  return (
    <div className="app">
      {busy && <div className="busy-bar" />}
      <TopBar onOpenSettings={() => openSettings("models")} />
      <Sidebar />
      <main className="main">
        <nav className="stepper">
          {STEPS.map((label, i) => (
            <Fragment key={label}>
              {i > 0 && <span className="step-arrow">›</span>}
              <div
                className={`step ${step === i ? "active" : ""} ${step > i ? "done" : ""}`}
                onClick={() => setStep(i)}
              >
                <span className="step-index">{step > i ? "✓" : i + 1}</span>
                <span>{label}</span>
              </div>
            </Fragment>
          ))}
        </nav>
        <div className="content">
          {!current ? (
            <div className="empty">
              <div className="big">🎬</div>
              <h3>{t("nav.noProject")}</h3>
              <p>{t("nav.noProjectHint")}</p>
            </div>
          ) : step === 0 ? (
            <StepUpload />
          ) : step === 1 ? (
            <StepSettings />
          ) : step === 2 ? (
            <StepReview />
          ) : (
            <StepExport />
          )}
        </div>
      </main>
      {showSettings && (
        <SettingsModal initialTab={settingsTab} onClose={() => setShowSettings(false)} />
      )}
      <Toasts />
    </div>
  );
}
