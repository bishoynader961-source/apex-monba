export const locales = ["en", "de", "es", "fr", "pt", "ar"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

// Endonyms shown in the language switcher (each name in its own language).
export const localeNames: Record<Locale, string> = {
  en: "English",
  de: "Deutsch",
  es: "Español",
  fr: "Français",
  pt: "Português",
  ar: "العربية",
};

export const rtlLocales: readonly Locale[] = ["ar"] as const;

export function isRTL(locale: Locale): boolean {
  return (rtlLocales as readonly string[]).includes(locale);
}

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (locales as readonly string[]).includes(value);
}
