import { useTranslation } from "@vns/i18n";
import { useStore } from "@/store/useStore";
import type { ProviderSpec } from "@/lib/types";

/** 厂商名称走 i18n 词典，未收录的退回接口返回的 name */
function providerName(p: ProviderSpec | undefined, t: (k: string) => string): string {
  if (!p) return "";
  const key = `providers.${p.id}`;
  const translated = t(key);
  return translated === key ? p.name : translated;
}

function localized(
  item: { name?: string; name_en?: string } | undefined,
  locale: string,
  fallback = "",
): string {
  if (!item) return fallback;
  return locale.startsWith("zh") ? (item.name ?? fallback) : (item.name_en ?? item.name ?? fallback);
}

export default function StepSettings() {
  const { t, i18n } = useTranslation();
  const current = useStore((s) => s.current);
  const catalog = useStore((s) => s.catalog);
  const patch = useStore((s) => s.patchProject);
  const runAnalysis = useStore((s) => s.runAnalysis);
  const busy = useStore((s) => s.busy);
  const locale = i18n.language ?? "zh-CN";

  if (!current || !catalog) return null;

  const analysisProvider = catalog.vision.find((p) => p.id === current.analysis_model);
  const scriptProvider = catalog.text.find((p) => p.id === current.script_model);
  const ttsProvider = catalog.tts.find((p) => p.id === current.tts_provider);

  const canAnalyze =
    Boolean(current.video_filename) &&
    (!analysisProvider?.requires_key || analysisProvider.key_present) &&
    !busy;

  return (
    <div>
      <div className="card">
        <h3 className="card-title">{t("settings.title")}</h3>
        <p className="card-desc">{t("settings.desc")}</p>

        <div className="grid-2">
          <div className="field">
            <label>{t("settings.analysisModel")}</label>
            <select
              value={current.analysis_model}
              onChange={(e) => void patch({ analysis_model: e.target.value })}
            >
              {catalog.vision.map((p) => (
                <option key={p.id} value={p.id}>
                  {providerName(p, t)}
                  {p.native_video ? ` (${t("settings.nativeVideo")})` : ""}
                  {p.key_present ? "" : p.requires_key ? ` (${t("settings.keyMissing")})` : ""}
                </option>
              ))}
            </select>
            <div className="hint" style={{ display: "flex", gap: 6, marginTop: 6 }}>
              {analysisProvider?.requires_key ? (
                analysisProvider.key_present ? (
                  <span className="tag ok">{t("settings.keyPresent")}</span>
                ) : (
                  <span className="tag warn">{t("settings.keyMissing")}</span>
                )
              ) : (
                <span className="tag">{t("settings.keyNotNeeded")}</span>
              )}
              {analysisProvider?.native_video && (
                <span className="tag accent">{t("settings.nativeVideo")}</span>
              )}
            </div>
            {analysisProvider && analysisProvider.models.length > 0 && (
              <select
                style={{ marginTop: 8 }}
                value={current.analysis_model_name || analysisProvider.default_model}
                onChange={(e) => void patch({ analysis_model_name: e.target.value })}
                aria-label={t("settings.modelName")}
              >
                {analysisProvider.models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            )}
            {analysisProvider?.note && <div className="hint">{analysisProvider.note}</div>}
          </div>

          <div className="field">
            <label>{t("settings.scriptModel")}</label>
            <select
              value={current.script_model}
              onChange={(e) => void patch({ script_model: e.target.value })}
            >
              <option value="">{t("settings.scriptModelNone")}</option>
              {catalog.text.map((p) => (
                <option key={p.id} value={p.id}>
                  {providerName(p, t)}
                  {p.key_present ? "" : p.requires_key ? ` (${t("settings.keyMissing")})` : ""}
                </option>
              ))}
            </select>
            <div className="hint" style={{ display: "flex", gap: 6, marginTop: 6 }}>
              {scriptProvider?.requires_key ? (
                scriptProvider.key_present ? (
                  <span className="tag ok">{t("settings.keyPresent")}</span>
                ) : (
                  <span className="tag warn">{t("settings.keyMissing")}</span>
                )
              ) : null}
            </div>
            {scriptProvider && scriptProvider.models.length > 0 && (
              <select
                style={{ marginTop: 8 }}
                value={current.script_model_name || scriptProvider.default_model}
                onChange={(e) => void patch({ script_model_name: e.target.value })}
                aria-label={t("settings.modelName")}
              >
                {scriptProvider.models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        <div className="grid-3">
          <div className="field">
            <label>{t("settings.asr")}</label>
            <select
              value={current.asr_provider}
              onChange={(e) => void patch({ asr_provider: e.target.value })}
            >
              {catalog.asr.map((a) => (
                <option key={a.id} value={a.id}>
                  {localized(a, locale, a.name)}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>{t("settings.tts")}</label>
            <select
              value={current.tts_provider}
              onChange={(e) => void patch({ tts_provider: e.target.value })}
            >
              {catalog.tts.map((p) => (
                <option key={p.id} value={p.id}>
                  {providerName(p, t)}
                </option>
              ))}
            </select>
            <div className="hint" style={{ display: "flex", gap: 6, marginTop: 6 }}>
              {ttsProvider?.requires_key ? (
                ttsProvider.key_present ? (
                  <span className="tag ok">{t("settings.keyPresent")}</span>
                ) : (
                  <span className="tag warn">{t("settings.keyMissing")}</span>
                )
              ) : (
                <span className="tag">{t("settings.keyNotNeeded")}</span>
              )}
            </div>
          </div>

          <div className="field">
            <label>{t("settings.aspect")}</label>
            <select value={current.aspect} onChange={(e) => void patch({ aspect: e.target.value })}>
              {catalog.aspects.map((a) => (
                <option key={a.id} value={a.id}>
                  {localized(a, locale, a.name)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">{t("settings.style")}</h3>
        <p className="card-desc">{t("settings.styleDesc")}</p>
        <div className="grid-3">
          {catalog.styles.map((s) => (
            <button
              key={s.id}
              className="card style-card"
              onClick={() => void patch({ style: s.id })}
              data-active={current.style === s.id}
            >
              <div className="style-name">{localized(s, locale, s.name)}</div>
              <div className="style-desc">
                {locale.startsWith("zh") ? s.desc : (s.desc_en ?? s.desc)}
              </div>
              <div className="style-sample">“{s.sample}”</div>
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">{t("settings.voice")}</h3>
        <div className="grid-3">
          <div className="field">
            <label>{t("settings.voiceName")}</label>
            <select
              value={current.voice_id}
              onChange={(e) => void patch({ voice_id: e.target.value })}
            >
              {catalog.voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} · {v.gender} · {v.tone}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>{t("settings.speed")}</label>
            <select
              value={current.voice_speed}
              onChange={(e) => void patch({ voice_speed: e.target.value })}
            >
              {["-20%", "-10%", "+0%", "+10%", "+20%", "+30%"].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>{t("settings.emotion")}</label>
            <select
              value={current.voice_emotion}
              onChange={(e) => void patch({ voice_emotion: e.target.value })}
            >
              {(locale.startsWith("zh") ? catalog.emotions : (catalog.emotions_en ?? catalog.emotions)).map(
                (e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                )
              )}
            </select>
          </div>
        </div>

        <div className="field" style={{ maxWidth: 280 }}>
          <label>{t("settings.narrationLanguage")}</label>
          <select
            value={current.language}
            onChange={(e) => void patch({ language: e.target.value })}
          >
            {(catalog.narration_languages ?? []).map((l) => (
              <option key={l.id} value={l.id}>
                {localized(l, locale, l.name)}
              </option>
            ))}
          </select>
          <div className="hint">{t("settings.narrationLanguageHint")}</div>
        </div>

        <div className="row wrap" style={{ gap: 18 }}>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={current.subtitle_enabled}
              onChange={(e) => void patch({ subtitle_enabled: e.target.checked })}
            />
            {t("settings.subtitleFile")}
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={current.burn_subtitles}
              onChange={(e) => void patch({ burn_subtitles: e.target.checked })}
            />
            {t("settings.burnSubtitles")}
          </label>
        </div>
      </div>

      <div className="card">
        <div className="row">
          <div>
            <h3 className="card-title" style={{ marginBottom: 2 }}>
              {t("settings.start")}
            </h3>
            <p className="card-desc" style={{ margin: 0 }}>
              {t("settings.startDesc")}
            </p>
          </div>
          <span className="spacer" />
          <button className="btn primary" disabled={!canAnalyze} onClick={() => void runAnalysis()}>
            {busy ? t("settings.analyzing") : t("settings.start")}
          </button>
        </div>
        {analysisProvider?.requires_key && !analysisProvider.key_present && (
          <div className="banner warn" style={{ marginTop: 14, marginBottom: 0 }}>
            {t("settings.missingKey", { name: providerName(analysisProvider, t) })}
          </div>
        )}
      </div>
    </div>
  );
}
