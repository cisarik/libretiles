// Picker row order. The four reviewed locales keep their original positions so no
// existing user's list is reordered under them; the eight that follow are in the
// order their catalogs were authored (de · pt · is · it · nl · da · sv · af), which
// makes the order derivable from the commit history rather than invented here.
export const LOCALES = [
  "en",
  "sk",
  "cs",
  "pl",
  "de",
  "pt",
  "is",
  "it",
  "nl",
  "da",
  "sv",
  "af",
] as const;
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

/**
 * Letters NFD + \p{Diacritic} CANNOT fold — they carry no combining mark — so an unfolded letter
 * leaves a picker row unreachable by any ASCII query. ł U+0142 L-STROKE, ø U+00F8 SLASHED O,
 * æ U+00E6 AE, þ U+00FE THORN, ß U+00DF SHARP S, œ U+0153 OE, ı U+0131 DOTLESS I, and the two
 * look-alikes ð U+00F0 ETH and đ U+0111 D-STROKE, different letters that each need their own
 * entry. Covers the languages this product targets and is NOT a complete inventory of unfoldable
 * Latin letters — extend it rather than assuming a letter is already handled.
 */
const EXPLICIT_SEARCH_FOLDS: Record<string, string> = {
  ł: "l",
  Ł: "l",
  đ: "d",
  Đ: "d",
  ø: "o",
  Ø: "o",
  æ: "ae",
  Æ: "ae",
  þ: "th",
  Þ: "th",
  ð: "d",
  Ð: "d",
  ß: "ss",
  œ: "oe",
  Œ: "oe",
  ı: "i",
};

export function foldForSearch(value: string): string {
  let mapped = "";
  for (const char of value) {
    mapped += EXPLICIT_SEARCH_FOLDS[char] ?? char;
  }
  return mapped.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
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
