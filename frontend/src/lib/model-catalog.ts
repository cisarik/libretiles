/**
 * Centralized free-rival catalog resolution.
 *
 * Exact direct/watchlist tuples are mirrored by the client-safe provider
 * registry, while OpenRouter keeps structural `vendor/model:free` support.
 * Every route still revalidates a tuple against live Django catalog rows.
 */

import { isValidRuntimePair } from "./provider-registry";

export {
  AION_MODEL_ID,
  AION_PROVIDER,
  CLOUDFLARE_WORKERS_AI_MODEL_ID,
  CLOUDFLARE_WORKERS_AI_PROVIDER,
  GOOGLE_GEMINI_MODEL_ID,
  GOOGLE_GEMINI_PROVIDER,
  GROQ_MODEL_ID,
  GROQ_PROVIDER,
  HUGGINGFACE_MODEL_ID,
  HUGGINGFACE_PROVIDER,
  IBM_WATSONX_MODEL_ID,
  IBM_WATSONX_PROVIDER,
  MISTRAL_MODEL_ID,
  MISTRAL_PROVIDER,
  NVIDIA_NIM_MODEL_ID,
  NVIDIA_NIM_PROVIDER,
  OPENROUTER_PROVIDER,
  isKnownProvider,
  isOpenRouterFreeId,
  isValidRuntimePair,
} from "./provider-registry";
export type { AiRuntimeProvider } from "./provider-registry";

export type CatalogPair = {
  provider: string;
  model_id: string;
};

export type CatalogModelRow = CatalogPair;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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
