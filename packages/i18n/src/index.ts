/**
 * i18n 入口。
 *
 * - 默认简体中文，可在顶栏一键切换英文；
 * - 界面语言与解说词语言互相独立（解说语言在项目设置里选择）。
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { en } from "./locales/en";
import { zhCN } from "./locales/zh-CN";

export const SUPPORTED_LOCALES = [
  { id: "zh-CN", label: "简体中文" },
  { id: "en", label: "English" },
] as const;

export type LocaleId = (typeof SUPPORTED_LOCALES)[number]["id"];

export const LOCALE_STORAGE_KEY = "vns_locale";

const resources = {
  "zh-CN": { translation: zhCN },
  en: { translation: en },
};

function detectLocale(): LocaleId {
  if (typeof window === "undefined") return "zh-CN";
  try {
    const saved = window.localStorage.getItem(LOCALE_STORAGE_KEY) as LocaleId | null;
    if (saved && SUPPORTED_LOCALES.some((l) => l.id === saved)) return saved;
  } catch {
    /* ignore */
  }
  const nav = window.navigator?.language ?? "zh-CN";
  return nav.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
}

export function initI18n() {
  if (!i18n.isInitialized) {
    void i18n.use(initReactI18next).init({
      resources,
      lng: detectLocale(),
      fallbackLng: "zh-CN",
      interpolation: { escapeValue: false },
      returnNull: false,
    });
  }
  // 同步 <html lang>，无障碍与浏览器翻译都依赖它
  if (typeof document !== "undefined") {
    document.documentElement.lang = i18n.language ?? "zh-CN";
  }
  i18n.on("languageChanged", (lng) => {
    if (typeof document !== "undefined") document.documentElement.lang = lng;
  });
  return i18n;
}

export function setLocale(locale: LocaleId) {
  void i18n.changeLanguage(locale);
  if (typeof document !== "undefined") {
    document.documentElement.lang = locale;
  }
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    /* ignore */
  }
}

export function getLocale(): LocaleId {
  return (i18n.language as LocaleId) ?? "zh-CN";
}

export { i18n };
export * from "react-i18next";
