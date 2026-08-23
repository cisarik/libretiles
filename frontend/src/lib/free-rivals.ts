export const DEFAULT_FREE_MODEL_ID = "google/gemma-4-31b-it:free" as const;

export const FREE_RIVAL_IDS = [
  "google/gemma-4-31b-it:free",
  "nvidia/nemotron-3-super-120b-a12b:free",
  "z-ai/glm-5.2:free",
  "google/gemma-4-26b-a4b-it:free",
] as const;

export type FreeRivalId = (typeof FREE_RIVAL_IDS)[number];

export function isFreeRivalId(value: unknown): value is FreeRivalId {
  return (
    typeof value === "string" &&
    (FREE_RIVAL_IDS as readonly string[]).includes(value)
  );
}

export function resolveFreeRivalId(raw: unknown): FreeRivalId {
  return isFreeRivalId(raw) ? raw : DEFAULT_FREE_MODEL_ID;
}
