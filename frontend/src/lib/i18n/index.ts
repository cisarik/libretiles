import { useEffect } from "react";
import {
  adoptBrowserLocaleIfUnset,
  useGameStore,
} from "@/hooks/useGameStore";
import {
  DEFAULT_LOCALE,
  detectBrowserLocale,
  isLocale,
  type Locale,
} from "./locales";
import { enFn, enText, type FnKey, type TextKey } from "./messages.en";
import { skFn, skText } from "./messages.sk";

export type { FnKey, TextKey } from "./messages.en";
export type { Locale } from "./locales";
export {
  DEFAULT_LOCALE,
  detectBrowserLocale,
  isLocale,
  LOCALE_COOKIE_NAME,
  LOCALES,
  localeFromCookieValue,
} from "./locales";
export { pluralEn, pluralSk } from "./plural";

function browserLanguages(): readonly string[] {
  if (typeof navigator === "undefined") return [];
  if (navigator.languages && navigator.languages.length > 0) {
    return Array.from(navigator.languages);
  }
  return navigator.language ? [navigator.language] : [];
}

export function t(locale: Locale, key: TextKey): string {
  return (locale === "sk" ? skText : enText)[key];
}

export function tf<K extends FnKey>(
  locale: Locale,
  key: K,
  params: Parameters<(typeof enFn)[K]>[0],
): string {
  const fn = (locale === "sk" ? skFn : enFn)[key];
  return fn(params);
}

export function useLocale(): Locale {
  const stored = useGameStore((s) => s.uiLocale);

  useEffect(() => {
    const apply = () => {
      adoptBrowserLocaleIfUnset(browserLanguages());
    };
    if (useGameStore.persist.hasHydrated()) {
      apply();
      return;
    }
    return useGameStore.persist.onFinishHydration(apply);
  }, []);

  if (isLocale(stored)) return stored;
  if (typeof navigator === "undefined") return DEFAULT_LOCALE;
  return detectBrowserLocale(browserLanguages());
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
