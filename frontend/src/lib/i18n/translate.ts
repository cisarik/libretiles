import { enFn, enText, type FnKey, type TextKey } from "./messages.en";
import { skFn, skText } from "./messages.sk";
import { csFn, csText } from "./messages.cs";
import { plFn, plText } from "./messages.pl";
import { deFn, deText } from "./messages.de";
import { ptFn, ptText } from "./messages.pt";
import { isFn, isText } from "./messages.is";
import { itFn, itText } from "./messages.it";
import { nlFn, nlText } from "./messages.nl";
import { daFn, daText } from "./messages.da";
import { svFn, svText } from "./messages.sv";
import { afFn, afText } from "./messages.af";
import type { Locale } from "./locales";

// Row order in both tables follows LOCALES. The tables are Record<Locale, …>, so
// the compiler does not care, but a reader diffing the three lists does.
const TEXT: Record<Locale, Record<TextKey, string>> = {
  en: enText,
  sk: skText,
  cs: csText,
  pl: plText,
  de: deText,
  pt: ptText,
  is: isText,
  it: itText,
  nl: nlText,
  da: daText,
  sv: svText,
  af: afText,
};
const FN: Record<Locale, typeof enFn> = {
  en: enFn,
  sk: skFn,
  cs: csFn,
  pl: plFn,
  de: deFn,
  pt: ptFn,
  is: isFn,
  it: itFn,
  nl: nlFn,
  da: daFn,
  sv: svFn,
  af: afFn,
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
  // parameters. The variance is confined to this one cast; every non-`en`
  // catalog — all eleven of them — is already pinned to `enFn`'s exact
  // signatures by its own mapped type, as `messages.sk.ts` is, so the cast
  // cannot hide a genuine mismatch between any two catalogs.
  const table = FN[locale];
  const fn = table[key] as (p: Parameters<(typeof enFn)[K]>[0]) => string;
  return fn(params);
}
