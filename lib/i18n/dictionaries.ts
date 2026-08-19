import en from "./locales/en.json";
import de from "./locales/de.json";
import es from "./locales/es.json";
import fr from "./locales/fr.json";
import pt from "./locales/pt.json";
import ar from "./locales/ar.json";

import type { Locale } from "./config";

// Every locale dictionary is keyed identically to `en` (enforced by the
// lib/i18n/i18n.test.ts completeness check). `t()` falls back to the key when a
// translation is missing, so a partial locale never crashes the UI.
export const dictionaries: Record<Locale, Record<string, string>> = {
  en,
  de,
  es,
  fr,
  pt,
  ar,
};
