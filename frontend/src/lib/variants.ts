import type { VariantSummary } from "@/lib/types";

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function isSyntacticallyValidSlug(value: unknown): value is string {
  return typeof value === "string" && SLUG_RE.test(value);
}

export function firstPlayableVariant(
  variants: readonly VariantSummary[],
): VariantSummary | null {
  return variants.find((row) => row.readiness === "playable") ?? null;
}

export function reconcileSelectedVariantSlug(
  current: string,
  variants: readonly VariantSummary[],
): string | null {
  const playable = firstPlayableVariant(variants);
  if (!playable) return null;
  const match = variants.find((row) => row.slug === current);
  if (match && match.readiness === "playable") return current;
  return playable.slug;
}
