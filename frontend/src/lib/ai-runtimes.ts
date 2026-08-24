import type { LanguageModel } from "ai";
import { getOpenRouterModel } from "./openrouter";
import { getNvidiaNimModel } from "./nvidia-nim";

export const OPENROUTER_PROVIDER = "openrouter" as const;
export const NVIDIA_NIM_PROVIDER = "nvidia-nim" as const;

export type AiRuntimeProvider =
  | typeof OPENROUTER_PROVIDER
  | typeof NVIDIA_NIM_PROVIDER;

export type FreeRivalPair = readonly [AiRuntimeProvider, string];

/** Keep in sync with backend/catalog/selection.py FREE_RIVAL_PAIRS. */
export const FREE_RIVAL_PAIRS: readonly FreeRivalPair[] = [
  [OPENROUTER_PROVIDER, "google/gemma-4-31b-it:free"],
  [NVIDIA_NIM_PROVIDER, "nvidia/nemotron-3-super-120b-a12b"],
  [OPENROUTER_PROVIDER, "nvidia/nemotron-3-super-120b-a12b:free"],
  [OPENROUTER_PROVIDER, "z-ai/glm-5.2:free"],
  [OPENROUTER_PROVIDER, "google/gemma-4-26b-a4b-it:free"],
];

export type CatalogModelRow = {
  provider: string;
  model_id: string;
};

export type NormalizedProviderError = {
  code:
    | "provider_auth_failed"
    | "provider_rate_limited"
    | "provider_unavailable";
  message: string;
};

const AUTH_MESSAGE =
  "This free rival could not authenticate. Switch to another free rival or retry later.";
const RATE_LIMIT_MESSAGE =
  "This free rival is rate limited. Switch to another free rival or retry later.";
const UNAVAILABLE_MESSAGE =
  "This free rival is temporarily unavailable. Switch to another free rival or retry later.";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isCuratedPair(provider: string, modelId: string): boolean {
  return FREE_RIVAL_PAIRS.some(
    ([entryProvider, entryModelId]) =>
      entryProvider === provider && entryModelId === modelId,
  );
}

export function findCuratedPair(
  modelId: string,
): { provider: AiRuntimeProvider; modelId: string } | null {
  const pair = FREE_RIVAL_PAIRS.find(([, entryModelId]) => entryModelId === modelId);
  return pair ? { provider: pair[0], modelId: pair[1] } : null;
}

export function parseCatalogModelRows(data: unknown): CatalogModelRow[] {
  if (!Array.isArray(data)) return [];
  const rows: CatalogModelRow[] = [];
  for (const item of data) {
    if (!isRecord(item)) continue;
    if (typeof item.provider !== "string" || typeof item.model_id !== "string") {
      continue;
    }
    rows.push({ provider: item.provider, model_id: item.model_id });
  }
  return rows;
}

/**
 * Accept only an exact pair present in both the curated registry and the
 * catalog list. Unknown or partial matches are rejected.
 */
export function revalidateRuntimePair(
  provider: string,
  modelId: string,
  catalogRows: CatalogModelRow[],
): boolean {
  if (!isCuratedPair(provider, modelId)) return false;
  return catalogRows.some(
    (row) => row.provider === provider && row.model_id === modelId,
  );
}

export function getLanguageModel(
  provider: string,
  modelId: string,
): LanguageModel {
  if (!isCuratedPair(provider, modelId)) {
    throw new Error("Unknown free-rival pair");
  }
  if (provider === NVIDIA_NIM_PROVIDER) {
    return getNvidiaNimModel(modelId);
  }
  return getOpenRouterModel(modelId);
}

/**
 * A legal backend terminal is only an ok:true place/pass/exchange payload.
 * ok:false, missing ok, and non-objects are not legal terminals.
 */
export function isLegalBackendTerminal(result: unknown): boolean {
  return isRecord(result) && result.ok === true;
}

function collectErrorGraph(error: unknown): {
  statuses: number[];
  haystack: string;
} {
  const statuses: number[] = [];
  const messages: string[] = [];
  const seen = new Set<unknown>();

  function visit(node: unknown): void {
    if (node === null || node === undefined) return;
    if (typeof node === "number" && Number.isFinite(node)) {
      statuses.push(node);
      return;
    }
    if (typeof node === "string") {
      messages.push(node);
      return;
    }
    if (typeof node !== "object") return;
    if (seen.has(node)) return;
    seen.add(node);

    const rec = node as Record<string, unknown>;
    if (typeof rec.statusCode === "number") statuses.push(rec.statusCode);
    if (typeof rec.status === "number") statuses.push(rec.status);
    if (typeof rec.message === "string") messages.push(rec.message);

    visit(rec.lastError);
    visit(rec.cause);
    if (Array.isArray(rec.errors)) {
      for (const item of rec.errors) visit(item);
    }
  }

  visit(error);
  return { statuses, haystack: messages.join(" ").toLowerCase() };
}

export function normalizeProviderError(
  error: unknown,
): NormalizedProviderError | null {
  const { statuses, haystack } = collectErrorGraph(error);

  if (
    statuses.includes(401) ||
    haystack.includes("unauthorized") ||
    haystack.includes("authentication failed") ||
    haystack.includes("invalid api key") ||
    haystack.includes("missing or invalid api key")
  ) {
    return { code: "provider_auth_failed", message: AUTH_MESSAGE };
  }

  if (
    statuses.includes(429) ||
    haystack.includes("rate limit") ||
    haystack.includes("too many requests")
  ) {
    return { code: "provider_rate_limited", message: RATE_LIMIT_MESSAGE };
  }

  const unavailableStatus = statuses.some((status) =>
    [402, 502, 503, 504].includes(status),
  );
  const unsupportedTools =
    (haystack.includes("unsupported") && haystack.includes("tool")) ||
    haystack.includes("tool use is not supported") ||
    haystack.includes("unsupported-tools");
  if (
    unavailableStatus ||
    unsupportedTools ||
    haystack.includes("overloaded") ||
    haystack.includes("overload") ||
    haystack.includes("insufficient funds") ||
    haystack.includes("payment required") ||
    haystack.includes("temporarily unavailable") ||
    haystack.includes("provider unavailable") ||
    haystack.includes("service unavailable")
  ) {
    return { code: "provider_unavailable", message: UNAVAILABLE_MESSAGE };
  }

  return null;
}
