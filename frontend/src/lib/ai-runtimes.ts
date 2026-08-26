import type { LanguageModel } from "ai";
import { getOpenRouterModel } from "./openrouter";
import { getNvidiaNimModel } from "./nvidia-nim";
import {
  ProviderRuntimeError,
  createProviderRequestTracker,
  getStandardOpenAICompatibleModel,
  type ProviderRequestTracker,
} from "./openai-compatible";
import {
  IBM_WATSONX_PROVIDER,
  NVIDIA_NIM_PROVIDER,
  OPENROUTER_PROVIDER,
  isValidRuntimePair,
  type CatalogModelRow,
} from "./model-catalog";

export {
  NVIDIA_NIM_MODEL_ID,
  NVIDIA_NIM_PROVIDER,
  OPENROUTER_PROVIDER,
  isValidRuntimePair,
  revalidateRuntimePair,
} from "./model-catalog";
export type {
  AiRuntimeProvider,
  CatalogModelRow,
} from "./model-catalog";
export type {
  NormalizedProviderUsage,
  ProviderRequestSnapshot,
  ProviderRequestTracker,
} from "./openai-compatible";

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

export function parseCatalogModelRows(data: unknown): CatalogModelRow[] {
  if (!Array.isArray(data)) return [];
  const rows: CatalogModelRow[] = [];
  for (const item of data) {
    if (typeof item !== "object" || item === null) continue;
    const record = item as Record<string, unknown>;
    if (typeof record.provider !== "string" || typeof record.model_id !== "string") {
      continue;
    }
    rows.push({ provider: record.provider, model_id: record.model_id });
  }
  return rows;
}

/**
 * Server-only runtime dispatch. Pair validation happens before any provider
 * configuration is read, and routes separately revalidate the same pair
 * against the live Django catalog.
 */
export async function getLanguageRuntime(
  provider: string,
  modelId: string,
): Promise<{ model: LanguageModel; tracker: ProviderRequestTracker }> {
  if (!isValidRuntimePair(provider, modelId)) {
    throw new Error("Unknown free-rival pair");
  }

  const tracker = createProviderRequestTracker();
  if (provider === NVIDIA_NIM_PROVIDER) {
    return { model: getNvidiaNimModel(modelId, tracker), tracker };
  }
  if (provider === OPENROUTER_PROVIDER) {
    return { model: getOpenRouterModel(modelId, tracker), tracker };
  }
  if (provider === IBM_WATSONX_PROVIDER) {
    // The IAM-aware watsonx adapter is intentionally isolated to the next
    // implementation slice. A prematurely activated row fails closed.
    throw new ProviderRuntimeError("provider_unavailable");
  }
  return {
    model: getStandardOpenAICompatibleModel(provider, modelId, tracker),
    tracker,
  };
}

/**
 * A legal backend terminal is only an ok:true place/pass/exchange payload.
 * ok:false, missing ok, and non-objects are not legal terminals.
 */
export function isLegalBackendTerminal(result: unknown): boolean {
  return (
    typeof result === "object" &&
    result !== null &&
    (result as Record<string, unknown>).ok === true
  );
}

function collectErrorGraph(error: unknown): {
  statuses: number[];
  codes: string[];
  haystack: string;
  hasProviderNotFound: boolean;
} {
  const statuses: number[] = [];
  const codes: string[] = [];
  const messages: string[] = [];
  const seen = new Set<unknown>();
  let hasProviderNotFound = false;

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
    if (typeof rec.code === "string") codes.push(rec.code.toLowerCase());
    if (typeof rec.message === "string") messages.push(rec.message);
    if (
      rec.name === "AI_APICallError" &&
      (rec.statusCode === 404 || rec.status === 404)
    ) {
      hasProviderNotFound = true;
    }

    visit(rec.lastError);
    visit(rec.cause);
    if (Array.isArray(rec.errors)) {
      for (const item of rec.errors) visit(item);
    }
  }

  visit(error);
  return {
    statuses,
    codes,
    haystack: messages.join(" ").toLowerCase(),
    hasProviderNotFound,
  };
}

export function normalizeProviderError(
  error: unknown,
): NormalizedProviderError | null {
  const { statuses, codes, haystack, hasProviderNotFound } =
    collectErrorGraph(error);

  if (
    statuses.includes(401) ||
    statuses.includes(403) ||
    codes.includes("provider_auth_failed") ||
    haystack.includes("unauthorized") ||
    haystack.includes("forbidden") ||
    haystack.includes("authentication failed") ||
    haystack.includes("invalid api key") ||
    haystack.includes("missing or invalid api key")
  ) {
    return { code: "provider_auth_failed", message: AUTH_MESSAGE };
  }

  if (
    statuses.includes(429) ||
    codes.includes("provider_rate_limited") ||
    haystack.includes("rate limit") ||
    haystack.includes("too many requests") ||
    haystack.includes("resource_exhausted") ||
    haystack.includes("resource exhausted")
  ) {
    return { code: "provider_rate_limited", message: RATE_LIMIT_MESSAGE };
  }

  const unavailableStatus = statuses.some((status) =>
    [402, 408, 502, 503, 504].includes(status),
  );
  const unsupportedTools =
    (haystack.includes("unsupported") && haystack.includes("tool")) ||
    haystack.includes("tool use is not supported") ||
    haystack.includes("unsupported-tools");
  const endpointRoutingUnavailable =
    haystack.includes("no endpoints found") ||
    haystack.includes(
      "no allowed providers are available for the selected model",
    );
  if (
    unavailableStatus ||
    codes.includes("provider_unavailable") ||
    hasProviderNotFound ||
    endpointRoutingUnavailable ||
    unsupportedTools ||
    haystack.includes("overloaded") ||
    haystack.includes("overload") ||
    haystack.includes("capacity") ||
    haystack.includes("model is unavailable") ||
    haystack.includes("model unavailable") ||
    haystack.includes("model_not_found") ||
    haystack.includes("deployment not found") ||
    haystack.includes("timed out") ||
    haystack.includes("timeout") ||
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
