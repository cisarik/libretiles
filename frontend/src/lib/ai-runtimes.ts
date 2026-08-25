import type { LanguageModel } from "ai";
import { getOpenRouterModel } from "./openrouter";
import { getNvidiaNimModel } from "./nvidia-nim";
import {
  NVIDIA_NIM_PROVIDER,
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
 * Runtime dispatch accepts only structurally valid free pairs: OpenRouter
 * native `vendor/model:free` IDs and the fixed NIM chat tuple.
 */
export function getLanguageModel(
  provider: string,
  modelId: string,
): LanguageModel {
  if (!isValidRuntimePair(provider, modelId)) {
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
  return (
    typeof result === "object" &&
    result !== null &&
    (result as Record<string, unknown>).ok === true
  );
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
