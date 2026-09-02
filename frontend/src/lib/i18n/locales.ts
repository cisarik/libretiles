export const LOCALES = ["en", "sk", "cs", "pl"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE_NAME = "libretiles_locale";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && LOCALES.includes(value as Locale);
}

export function detectBrowserLocale(languages: readonly string[]): Locale {
  for (const raw of languages) {
    if (typeof raw !== "string") continue;
    const primary = raw.trim().split(/[-_]/)[0]?.toLowerCase();
    if (isLocale(primary)) return primary;
  }
  return DEFAULT_LOCALE;
}

export function localeFromCookieValue(value: unknown): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE;
}

export function writeLocaleCookie(locale: Locale): void {
  if (typeof document === "undefined") return;
  document.cookie = `${LOCALE_COOKIE_NAME}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`;
}

export interface LocaleSyncDecision {
  cookie: Locale | null;
  refresh: boolean;
}

export function localeSyncDecision(
  serverLocale: Locale,
  resolvedLocale: Locale,
): LocaleSyncDecision {
  if (serverLocale === resolvedLocale) return { cookie: null, refresh: false };
  return { cookie: resolvedLocale, refresh: true };
}
