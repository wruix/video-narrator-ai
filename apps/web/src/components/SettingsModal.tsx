import { useEffect, useState } from "react";
import { useTranslation } from "@vns/i18n";
import { Modal } from "@vns/ui";
import { api, getToken, setToken as saveToken } from "@/lib/api";
import { useStore } from "@/store/useStore";
import type { ProviderSpec, UsageSummary } from "@/lib/types";

type Tab = "models" | "tts" | "usage" | "system";

export default function SettingsModal({
  onClose,
  initialTab = "models",
}: {
  onClose: () => void;
  initialTab?: Tab;
}) {
  const { t } = useTranslation();
  const catalog = useStore((s) => s.catalog);
  const health = useStore((s) => s.health);
  const toast = useStore((s) => s.toast);
  const bootstrap = useStore((s) => s.bootstrap);
  const setNeedsToken = useStore((s) => s.setNeedsToken);
  const [tab, setTab] = useState<Tab>(initialTab);
  const [scope, setScope] = useState<"user" | "server">("user");
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { ok: boolean; message: string }>>({});
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [token, setToken] = useState(getToken());
  const [tokenError, setTokenError] = useState("");

  useEffect(() => {
    if (tab === "usage") {
      api.usage().then(setUsage).catch(() => undefined);
    }
  }, [tab]);

  // 保存口令并重试；未启用鉴权时同样适用（服务端直接放行）
  const applyTokenNow = async (clear = false) => {
    const value = clear ? "" : token.trim();
    saveToken(value);
    setToken(value);
    setTokenError("");
    try {
      await api.providers();
      setNeedsToken(false);
      await bootstrap();
      toast("success", clear ? t("settingsModal.tokenCleared") : t("settingsModal.tokenSaved"));
      onClose();
    } catch (e) {
      setTokenError(t("settingsModal.tokenInvalid", { msg: (e as Error).message }));
    }
  };

  const refreshCatalog = async () => {
    const c = await api.providers();
    useStore.setState({ catalog: c });
  };

  const providerName = (p: ProviderSpec | undefined) => {
    if (!p) return "";
    const key = `providers.${p.id}`;
    const translated = t(key);
    return translated === key ? p.name : translated;
  };

  const saveKey = async (provider: string) => {
    const value = (inputs[provider] ?? "").trim();
    if (!value) return;
    setBusy(provider);
    try {
      await api.setKey(provider, value, scope);
      setInputs((s) => ({ ...s, [provider]: "" }));
      toast(
        "success",
        t("settingsModal.saved", {
          scope: scope === "user" ? t("settingsModal.scopeUser") : t("settingsModal.scopeServer"),
        }),
      );
      await refreshCatalog();
    } catch (e) {
      toast("error", t("errors.saveKeyFailed", { msg: (e as Error).message }));
    } finally {
      setBusy(null);
    }
  };

  const removeKey = async (provider: string) => {
    setBusy(provider);
    try {
      await api.deleteKey(provider, scope);
      toast("success", t("settingsModal.deleted"));
      await refreshCatalog();
    } catch (e) {
      toast("error", t("errors.deleteKeyFailed", { msg: (e as Error).message }));
    } finally {
      setBusy(null);
    }
  };

  const testKey = async (p: ProviderSpec) => {
    const kind =
      p.kind === "tts" ? "tts" : ["gemini", "qwen", "doubao"].includes(p.id) ? "vision" : "text";
    setBusy(p.id);
    try {
      const res = await api.testConnection(p.id, kind);
      setResults((r) => ({ ...r, [p.id]: { ok: res.ok, message: res.message } }));
    } catch (e) {
      setResults((r) => ({ ...r, [p.id]: { ok: false, message: (e as Error).message } }));
    } finally {
      setBusy(null);
    }
  };

  const renderProvider = (p: ProviderSpec) => {
    const res = results[p.id];
    return (
      <div key={p.id} className="model-row">
        <div className="info">
          <div className="n">
            {providerName(p)}
            {p.native_video && <span className="tag accent">{t("settings.nativeVideo")}</span>}
            {p.requires_key ? (
              p.key_present ? (
                <span className="tag ok">
                  {p.key_source === "server"
                    ? t("settingsModal.scopeServer")
                    : t("settingsModal.scopeUser")}{" "}
                  {p.key_masked}
                </span>
              ) : (
                <span className="tag warn">{t("settingsModal.notConfigured")}</span>
              )
            ) : (
              <span className="tag">{t("settings.keyNotNeeded")}</span>
            )}
          </div>
          <div className="d">
            {p.note || p.key_hint}
            {p.models.length ? ` · ${p.default_model}` : ""}
          </div>
          {res && (
            <div className="d" style={{ color: res.ok ? "var(--accent-2)" : "var(--danger)" }}>
              {res.ok ? "✓" : "✗"} {res.message}
            </div>
          )}
        </div>
        {p.requires_key ? (
          <div className="row" style={{ width: 340, flexShrink: 0 }}>
            <input
              type="password"
              placeholder={t("settingsModal.keyPlaceholder", { hint: p.key_hint })}
              value={inputs[p.id] ?? ""}
              onChange={(e) => setInputs((s) => ({ ...s, [p.id]: e.target.value }))}
              onKeyDown={(e) => {
                if (e.key === "Enter") void saveKey(p.id);
              }}
            />
            <button className="btn sm" disabled={busy === p.id} onClick={() => void saveKey(p.id)}>
              {t("common.save")}
            </button>
            <button
              className="btn sm"
              disabled={busy === p.id || !p.key_present}
              onClick={() => void testKey(p)}
            >
              {t("common.test")}
            </button>
            <button
              className="btn sm danger"
              disabled={busy === p.id || !p.key_present}
              onClick={() => void removeKey(p.id)}
              title={t("common.delete")}
            >
              ✕
            </button>
          </div>
        ) : (
          <button className="btn sm" disabled={busy === p.id} onClick={() => void testKey(p)}>
            {t("common.test")}
          </button>
        )}
      </div>
    );
  };

  const tabs: { id: Tab; label: string }[] = catalog
    ? [
        { id: "models", label: t("settingsModal.models") },
        { id: "tts", label: t("settingsModal.tts") },
        { id: "usage", label: t("settingsModal.usage") },
        { id: "system", label: t("settingsModal.system") },
      ]
    : [
        { id: "system", label: t("settingsModal.access") },
        { id: "usage", label: t("settingsModal.usage") },
      ];

  // 没有 catalog 说明还没通过鉴权，只显示口令输入
  if (!catalog) {
    return (
      <Modal
        title={t("settingsModal.needsTokenTitle")}
        width={520}
        onClose={onClose}
        footer={
          <>
            <button className="btn" onClick={onClose}>
              {t("common.cancel")}
            </button>
            <button className="btn primary" onClick={() => void applyTokenNow()}>
              {t("settingsModal.unlock")}
            </button>
          </>
        }
      >
        <div className="banner warn">{t("settingsModal.needsTokenDesc")}</div>
        <div className="field">
          <label>{t("settingsModal.tokenTitle")}</label>
          <input
            type="password"
            autoFocus
            placeholder={t("settingsModal.tokenPlaceholder")}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void applyTokenNow();
            }}
          />
        </div>
        {tokenError && <div className="banner err">{tokenError}</div>}
      </Modal>
    );
  }

  return (
    <Modal
      title={t("settingsModal.title")}
      onClose={onClose}
      footer={
        <button className="btn" onClick={onClose}>
          {t("common.close")}
        </button>
      }
    >
      <div className="tabs">
        {tabs.map((tb) => (
          <div
            key={tb.id}
            className={`tab ${tab === tb.id ? "active" : ""}`}
            onClick={() => setTab(tb.id)}
          >
            {tb.label}
          </div>
        ))}
      </div>

      {tab === "models" && (
        <>
          <div className="banner info">{t("settingsModal.modeA")}</div>
          <div className="row" style={{ marginBottom: 14 }}>
            <span style={{ fontSize: 12.5, color: "var(--fg-1)" }}>
              {t("settingsModal.scope")}
            </span>
            <div className="row" style={{ gap: 6 }}>
              <button
                className={`btn sm ${scope === "user" ? "primary" : ""}`}
                onClick={() => setScope("user")}
              >
                {t("settingsModal.scopeUser")}
              </button>
              <button
                className={`btn sm ${scope === "server" ? "primary" : ""}`}
                onClick={() => setScope("server")}
              >
                {t("settingsModal.scopeServer")}
              </button>
            </div>
          </div>
          <div className="hint" style={{ marginBottom: 6 }}>
            {scope === "user" ? t("settingsModal.ownHint") : t("settingsModal.modeBHint")}
          </div>
          <h4 style={{ margin: "18px 0 4px", fontSize: 13.5 }}>{t("settingsModal.models")}</h4>
          {catalog.vision.map(renderProvider)}
        </>
      )}

      {tab === "tts" && (
        <>
          <div className="banner info">{t("settingsModal.edgeHint")}</div>
          {catalog.tts.map(renderProvider)}
        </>
      )}

      {tab === "usage" && (
        <>
          {!usage ? (
            <p style={{ color: "var(--fg-2)" }}>{t("common.loading")}</p>
          ) : (
            <>
              <div className="stat-grid" style={{ marginBottom: 16 }}>
                <div className="stat">
                  <div className="k">{t("settingsModal.totalTokens")}</div>
                  <div className="v">{usage.total_tokens.toLocaleString()}</div>
                </div>
                <div className="stat">
                  <div className="k">{t("settingsModal.totalSeconds")}</div>
                  <div className="v">{usage.total_seconds.toFixed(0)}s</div>
                </div>
                <div className="stat">
                  <div className="k">{t("settingsModal.calls")}</div>
                  <div className="v">{usage.items.length}</div>
                </div>
              </div>
              {usage.items.length === 0 ? (
                <p style={{ color: "var(--fg-2)" }}>{t("settingsModal.noUsage")}</p>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                  <thead>
                    <tr style={{ color: "var(--fg-2)", textAlign: "left" }}>
                      <th style={{ padding: "6px 4px" }}>{t("settingsModal.models")}</th>
                      <th style={{ padding: "6px 4px" }}>Model</th>
                      <th style={{ padding: "6px 4px" }}>Kind</th>
                      <th style={{ padding: "6px 4px" }}>Usage</th>
                      <th style={{ padding: "6px 4px" }}>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.items.map((u) => (
                      <tr key={u.id} style={{ borderTop: "1px solid var(--line-soft)" }}>
                        <td style={{ padding: "5px 4px" }}>{u.provider}</td>
                        <td style={{ padding: "5px 4px" }}>{u.model}</td>
                        <td style={{ padding: "5px 4px" }}>{u.kind}</td>
                        <td style={{ padding: "5px 4px" }}>
                          {u.units} {u.unit_name === "tokens" ? "tok" : "s"}
                        </td>
                        <td style={{ padding: "5px 4px", color: "var(--fg-2)" }}>
                          {u.created_at ? new Date(u.created_at).toLocaleString() : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </>
      )}

      {tab === "system" && (
        <>
          <h4 style={{ margin: "0 0 8px", fontSize: 13.5 }}>{t("settingsModal.tokenTitle")}</h4>
          <p style={{ fontSize: 12.5, color: "var(--fg-2)", margin: "0 0 12px" }}>
            {t("settingsModal.tokenDesc")}
          </p>
          <div className="row" style={{ marginBottom: 20 }}>
            <input
              type="password"
              placeholder={t("settingsModal.tokenPlaceholder")}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void applyTokenNow();
              }}
            />
            <button className="btn sm" onClick={() => void applyTokenNow()}>
              {t("settingsModal.tokenSave")}
            </button>
            {token && (
              <button className="btn sm ghost" onClick={() => void applyTokenNow(true)}>
                {t("common.clear")}
              </button>
            )}
          </div>
          {tokenError && (
            <div className="banner err" style={{ marginBottom: 16 }}>
              {tokenError}
            </div>
          )}

          <h4 style={{ margin: "0 0 8px", fontSize: 13.5 }}>{t("settingsModal.system")}</h4>
          <div className="kv-list">
            <div className="kv">
              <span className="k">{t("settingsModal.version")}</span>
              <span>{health?.version ?? "—"}</span>
            </div>
            <div className="kv">
              <span className="k">{t("settingsModal.ffmpeg")}</span>
              <span style={{ color: health?.ffmpeg ? "var(--accent-2)" : "var(--danger)" }}>
                {health?.ffmpeg ?? health?.ffmpeg_error ?? "—"}
              </span>
            </div>
            <div className="kv">
              <span className="k">{t("settingsModal.ffprobe")}</span>
              <span style={{ color: health?.ffprobe ? "var(--accent-2)" : "var(--danger)" }}>
                {health?.ffprobe ?? health?.ffprobe_error ?? "—"}
              </span>
            </div>
            <div className="kv">
              <span className="k">{t("settingsModal.modelCount")}</span>
              <span>
                {catalog.vision.length} · {catalog.tts.length}
              </span>
            </div>
            <div className="kv">
              <span className="k">{t("settingsModal.voiceCount")}</span>
              <span>{catalog.voices.length}</span>
            </div>
            <div className="kv">
              <span className="k">{t("settingsModal.address")}</span>
              <span>{window.location.origin}</span>
            </div>
          </div>
        </>
      )}
    </Modal>
  );
}
