import { enFn, enText, type FnKey, type TextKey } from "./messages.en";
import { skFn, skText } from "./messages.sk";
import { csFn, csText } from "./messages.cs";
import { plFn, plText } from "./messages.pl";
import type { Locale } from "./locales";

const TEXT: Record<Locale, Record<TextKey, string>> = {
  en: enText,
  sk: skText,
  cs: csText,
  pl: plText,
};
const FN: Record<Locale, typeof enFn> = {
  en: enFn,
  sk: skFn,
  cs: csFn,
  pl: plFn,
};

export function t(locale: Locale, key: TextKey): string {
  return TEXT[locale][key];
}

export function tf<K extends FnKey>(
  locale: Locale,
  key: K,
  params: Parameters<(typeof enFn)[K]>[0],
): string {
  // The PUBLIC signature above is what gives callers exact per-key parameter
  // checking, and it must not be weakened. Inside, indexing a table of
  // differently-parameterised functions by a generic key yields a UNION of
  // function types, and calling a union requires the INTERSECTION of its
  // parameter types. That is unsatisfiable once two keys take different
  // parameters. The variance is confined to this one cast; `skFn` is already
  // pinned to `enFn`'s exact signatures by its mapped type in messages.sk.ts,
  // so the cast cannot hide a genuine mismatch between the two catalogs.
  const table = FN[locale];
  const fn = table[key] as (p: Parameters<(typeof enFn)[K]>[0]) => string;
  return fn(params);
}
