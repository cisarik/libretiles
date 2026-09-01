export function pluralSk(n: number, one: string, few: string, many: string): string {
  const count = Math.abs(Math.trunc(n));
  if (count === 1) return one;
  if (count >= 2 && count <= 4) return few;
  return many;
}

export function pluralEn(n: number, one: string, other: string): string {
  return Math.abs(Math.trunc(n)) === 1 ? one : other;
}
