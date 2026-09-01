export const LOCALES = ["en", "sk"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE_NAME = "libretiles_locale";

export function isLocale(value: unknown): value is Locale {
  return value === "en" || value === "sk";
}

export function detectBrowserLocale(languages: readonly string[]): Locale {
  for (const raw of languages) {
    if (typeof raw !== "string") continue;
    const primary = raw.trim().split(/[-_]/)[0]?.toLowerCase();
    if (primary === "sk") return "sk";
  }
  return DEFAULT_LOCALE;
}

export function localeFromCookieValue(value: unknown): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE;
}
