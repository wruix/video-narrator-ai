# @vns/i18n

Interface translations for VideoNarrator AI.

## Locales

| id | Label |
| --- | --- |
| `zh-CN` | 简体中文 |
| `en` | English |

The interface language is **independent** from the narration language. A Chinese
interface can produce an English voice-over, and vice versa.

## Adding a string

1. Add the key to `src/locales/zh-CN.ts`.
2. Add the same key to `src/locales/en.ts`.
3. Use it in a component: `const { t } = useTranslation(); t("mySection.myKey")`.

The `TranslationSchema` type is derived from the Chinese file with string literals
widened, so the type checker enforces that both locales have the same key structure
while still allowing different wording.

## API

```ts
import { initI18n, setLocale, getLocale, SUPPORTED_LOCALES, useTranslation } from "@vns/i18n";

initI18n();                     // call once before rendering
setLocale("en");                // switch and persist to localStorage
getLocale();                    // "en"
```

The active language is stored under `vns_locale` in `localStorage` and falls back to the
browser's language.

## Licence

Apache-2.0, same as the parent repository.
