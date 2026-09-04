import { useGameStore } from "@/hooks/useGameStore";
import { useServerLocale } from "./LocaleProvider";
import {
  DEFAULT_LOCALE,
  isLocale,
  type Locale,
} from "./locales";
import { enFn, type FnKey, type TextKey } from "./messages.en";
import { t, tf } from "./translate";

export type { FnKey, TextKey } from "./messages.en";
export type { Locale } from "./locales";
export {
  DEFAULT_LOCALE,
  detectBrowserLocale,
  isLocale,
  LOCALE_COOKIE_NAME,
  LOCALES,
  localeFromCookieValue,
  localeSyncDecision,
  writeLocaleCookie,
} from "./locales";
export { t, tf } from "./translate";
export {
  pluralAf,
  pluralCs,
  pluralDa,
  pluralDe,
  pluralEn,
  pluralIs,
  pluralIt,
  pluralNl,
  pluralPl,
  pluralPt,
  pluralSk,
  pluralSv,
} from "./plural";

export function useLocale(): Locale {
  const server = useServerLocale();
  const stored = useGameStore((s) => s.uiLocale);
  if (server) return server;
  return isLocale(stored) ? stored : DEFAULT_LOCALE;
}

export function useT(): {
  t: (k: TextKey) => string;
  tf: <K extends FnKey>(k: K, p: Parameters<(typeof enFn)[K]>[0]) => string;
} {
  const locale = useLocale();
  return {
    t: (k) => t(locale, k),
    tf: (k, p) => tf(locale, k, p),
  };
}
