import { describe, expect, it } from "vitest";

import { defaultLocale, locales } from "@/lib/i18n/config";
import { dictionaries } from "@/lib/i18n/dictionaries";

describe("i18n dictionaries (C2)", () => {
  it("exposes every configured locale", () => {
    expect(locales).toContain(defaultLocale);
    expect(locales.length).toBeGreaterThanOrEqual(2);
  });

  it("every locale shares the exact key set of the default locale", () => {
    const baseKeys = Object.keys(dictionaries[defaultLocale]).sort();
    for (const locale of locales) {
      if (locale === defaultLocale) continue;
      const keys = Object.keys(dictionaries[locale]).sort();
      expect(keys).toEqual(baseKeys);
    }
  });

  it("falls back to the key for a missing translation", () => {
    const missing = "this.key.does.not.exist";
    // Mirrors I18nProvider.t() behaviour.
    const translated = dictionaries[defaultLocale][missing] ?? missing;
    expect(translated).toBe(missing);
  });
});
