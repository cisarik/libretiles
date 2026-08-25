/**
 * Centralized free-rival catalog resolution.
 *
 * There is no static frontend allowlist of model IDs. Structural validity,
 * preference resolution, and catalog revalidation all live here so Play and
 * Judge share exactly one source of truth.
 */

export const OPENROUTER_PROVIDER = "openrouter" as const;
export const NVIDIA_NIM_PROVIDER = "nvidia-nim" as const;

export type AiRuntimeProvider =
  | typeof OPENROUTER_PROVIDER
  | typeof NVIDIA_NIM_PROVIDER;

/** Fixed seeded NIM chat tuple. NIM has no catalog discovery. */
export const NVIDIA_NIM_MODEL_ID = "nvidia/nemotron-3-super-120b-a12b" as const;

/** Backend selection excludes this meta-row explicitly; mirror it here. */
const EXCLUDED_OPENROUTER_IDS: ReadonlySet<string> = new Set([
  "openrouter/free",
]);

export type CatalogPair = {
  provider: string;
  model_id: string;
};

export type CatalogModelRow = CatalogPair;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isKnownProvider(provider: string): provider is AiRuntimeProvider {
  return (
    provider === OPENROUTER_PROVIDER || provider === NVIDIA_NIM_PROVIDER
  );
}

/** OpenRouter runtime IDs must be native `vendor/model:free` identifiers. */
export function isOpenRouterFreeId(modelId: string): boolean {
  if (!modelId.includes("/")) return false;
  if (!modelId.endsWith(":free")) return false;
  return !EXCLUDED_OPENROUTER_IDS.has(modelId);
}

/**
 * Structural pair validity without a catalog: OpenRouter accepts only
 * catalog-confirmed `:free` shapes, NIM accepts only its fixed tuple.
 */
export function isValidRuntimePair(provider: string, modelId: string): boolean {
  if (!isKnownProvider(provider)) return false;
  if (provider === NVIDIA_NIM_PROVIDER) {
    return modelId === NVIDIA_NIM_MODEL_ID;
  }
  return isOpenRouterFreeId(modelId);
}

/** Accept only an exact structurally valid pair confirmed by catalog rows. */
export function revalidateRuntimePair(
  provider: string,
  modelId: string,
  catalogRows: CatalogModelRow[],
): boolean {
  if (!isValidRuntimePair(provider, modelId)) return false;
  return catalogRows.some(
    (row) => row.provider === provider && row.model_id === modelId,
  );
}

/**
 * Filter raw catalog rows down to playable pairs. Rows come from the backend
 * eligibility pipeline already; this is defense-in-depth that fails closed on
 * paid, malformed, unknown-provider, or excluded rows.
 */
export function playableCatalogPairs(
  catalogRows: CatalogModelRow[],
): CatalogPair[] {
  const pairs: CatalogPair[] = [];
  for (const row of catalogRows) {
    if (!isRecord(row)) continue;
    if (typeof row.provider !== "string" || typeof row.model_id !== "string") {
      continue;
    }
    if (!isValidRuntimePair(row.provider, row.model_id)) continue;
    pairs.push({ provider: row.provider, model_id: row.model_id });
  }
  return pairs;
}

export function findCatalogPair(
  modelId: string | null | undefined,
  catalogRows: CatalogModelRow[],
): CatalogPair | null {
  if (!modelId) return null;
  return (
    playableCatalogPairs(catalogRows).find(
      (row) => row.model_id === modelId,
    ) ?? null
  );
}

/**
 * Shared preference resolution: valid server preference first, then the valid
 * locally stored selection, then catalog row 1 (newest). Returns null only
 * when the catalog itself is empty.
 */
export function resolveEligibleModelId(
  eligibleIds: string[],
  preferredId: string | null | undefined,
  storedId: string | null | undefined,
): string | null {
  if (preferredId && eligibleIds.includes(preferredId)) return preferredId;
  if (storedId && eligibleIds.includes(storedId)) return storedId;
  return eligibleIds[0] ?? null;
}


