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
