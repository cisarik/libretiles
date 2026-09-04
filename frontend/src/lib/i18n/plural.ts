export function pluralSk(n: number, one: string, few: string, many: string): string {
  const count = Math.abs(Math.trunc(n));
  if (count === 1) return one;
  if (count >= 2 && count <= 4) return few;
  return many;
}

export function pluralEn(n: number, one: string, other: string): string {
  return Math.abs(Math.trunc(n)) === 1 ? one : other;
}

export function pluralPl(n: number, one: string, few: string, many: string): string {
  const count = Math.abs(Math.trunc(n));
  if (count === 1) return one;
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return few;
  return many;
}

// Slovak and Czech share the integer 1 / 2..4 / otherwise rule; reusing
// pluralSk is deliberate rather than an accident.
export const pluralCs = pluralSk;

// The eight helpers below carry CLDR category NAMES in their parameter names and
// are ordered one -> other -> many, so the fallback slot is `other` rather than
// the last parameter. That differs on purpose from pluralSk / pluralPl above,
// whose third slot is named `many` while over the integers it is CLDR `other`.
//
// af / nl / de / da / sv have five separate bodies rather than aliases of
// pluralEn. Over the INTEGERS they agree with English exactly (measured: zero
// divergences over 0..3000), but the CLDR rules differ on fractions — Danish is
// `n = 1 or t != 0 and i = 0,1`, so CLDR da 0.5 is `one` while en 0.5 is
// `other`. These helpers truncate, which is what makes the integer identity a
// property of the code. An alias would let a future CLDR divergence in one of
// them silently change English, the one language here with reviewed copy.
// GLOSSARY.md D7 records the same rule: do not fold them into one table-driven
// function.

// CLDR af: one <=> i = 1; otherwise other.
export function pluralAf(n: number, one: string, other: string): string {
  return Math.abs(Math.trunc(n)) === 1 ? one : other;
}

// CLDR nl: one <=> i = 1; otherwise other.
export function pluralNl(n: number, one: string, other: string): string {
  return Math.abs(Math.trunc(n)) === 1 ? one : other;
}

// CLDR de: one <=> i = 1; otherwise other.
export function pluralDe(n: number, one: string, other: string): string {
  return Math.abs(Math.trunc(n)) === 1 ? one : other;
}

// CLDR da: one <=> i = 1; otherwise other. (CLDR also selects `one` for some
// fractions; this helper truncates, so the integer rule is the whole rule.)
export function pluralDa(n: number, one: string, other: string): string {
  return Math.abs(Math.trunc(n)) === 1 ? one : other;
}

// CLDR sv: one <=> i = 1; otherwise other.
export function pluralSv(n: number, one: string, other: string): string {
  return Math.abs(Math.trunc(n)) === 1 ? one : other;
}

// CLDR is: one <=> i % 10 = 1 and i % 100 != 11; otherwise other.
// This is NOT the Nordic one/other shape: 1 21 31 101 121 1001 are `one`, and
// 0 11 111 1011 are `other`. Do not copy it from pluralDa or pluralSv.
export function pluralIs(n: number, one: string, other: string): string {
  const count = Math.abs(Math.trunc(n));
  return count % 10 === 1 && count % 100 !== 11 ? one : other;
}

// CLDR it: one <=> i = 1; many <=> i % 1000000 = 0 and i != 0; otherwise other.
// `many` is reachable only at exact millions, and it may legitimately carry the
// same noun form as `other`.
export function pluralIt(
  n: number,
  one: string,
  other: string,
  many: string,
): string {
  const count = Math.abs(Math.trunc(n));
  if (count === 1) return one;
  if (count !== 0 && count % 1000000 === 0) return many;
  return other;
}

// CLDR pt: one <=> i = 0 or i = 1 — ZERO IS SINGULAR, so "0 ponto" and not
// "0 pontos". many <=> i % 1000000 = 0 and i != 0; otherwise other.
export function pluralPt(
  n: number,
  one: string,
  other: string,
  many: string,
): string {
  const count = Math.abs(Math.trunc(n));
  if (count === 0 || count === 1) return one;
  if (count % 1000000 === 0) return many;
  return other;
}
