/** Server-side helpers for OpenAI-compatible free-rival transports. */

import { createOpenAI } from "@ai-sdk/openai";
import type { LanguageModel } from "ai";
import {
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
  MISTRAL_MODEL_ID,
  MISTRAL_PROVIDER,
} from "./provider-registry";

const AUTH_MESSAGE =
  "This free rival could not authenticate. Switch to another free rival or retry later.";
const UNAVAILABLE_MESSAGE =
  "This free rival is temporarily unavailable. Switch to another free rival or retry later.";

const MAX_TRACKED_REQUESTS = 10_000;
const MAX_TRACKED_TOKENS = 1_000_000_000;
const MAX_RETRY_AFTER_SECONDS = 86_400;

type RuntimeErrorCode = "provider_auth_failed" | "provider_unavailable";

export class ProviderRuntimeError extends Error {
  readonly code: RuntimeErrorCode;

  constructor(code: RuntimeErrorCode) {
    super(code === "provider_auth_failed" ? AUTH_MESSAGE : UNAVAILABLE_MESSAGE);
    this.name = "ProviderRuntimeError";
    this.code = code;
  }
}

export type NormalizedProviderUsage = Readonly<{
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}>;

export type ProviderRequestSnapshot = Readonly<{
  provider_requests: number;
  usage?: NormalizedProviderUsage;
  retry_after_seconds?: number;
}>;

export interface ProviderRequestTracker {
  /** Count immediately before an actual provider/IAM fetch leaves the app. */
  noteProviderRequest(): void;
  /** Record only normalized numeric usage; raw provider metadata is discarded. */
  recordUsage(usage: unknown): void;
  /** Capture one Retry-After value without retaining the raw header. */
  recordRetryAfter(value: string | null, nowMs?: number): void;
  /** Return bounded numeric telemetry only. */
  snapshot(): ProviderRequestSnapshot;
}

function boundedInteger(value: unknown, maximum: number): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return null;
  }
  return Math.min(Math.floor(value), maximum);
}

function tokenTotal(value: unknown): number | null {
  const direct = boundedInteger(value, MAX_TRACKED_TOKENS);
  if (direct !== null) return direct;
  if (typeof value !== "object" || value === null) return null;
  return boundedInteger(
    (value as Record<string, unknown>).total,
    MAX_TRACKED_TOKENS,
  );
}

function normalizeTrackedUsage(usage: unknown): NormalizedProviderUsage | null {
  if (typeof usage !== "object" || usage === null) return null;
  const record = usage as Record<string, unknown>;
  const inputTokens = tokenTotal(record.inputTokens) ?? 0;
  const outputTokens = tokenTotal(record.outputTokens) ?? 0;
  const totalTokens =
    boundedInteger(record.totalTokens, MAX_TRACKED_TOKENS) ??
    Math.min(inputTokens + outputTokens, MAX_TRACKED_TOKENS);
  if (inputTokens === 0 && outputTokens === 0 && totalTokens === 0) return null;
  return {
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    total_tokens: totalTokens,
  };
}

function parseRetryAfterSeconds(value: string, nowMs: number): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;

  const delta = Number(trimmed);
  if (Number.isFinite(delta) && delta >= 0) {
    return Math.min(Math.ceil(delta), MAX_RETRY_AFTER_SECONDS);
  }

  const atMs = Date.parse(trimmed);
  if (!Number.isFinite(atMs)) return null;
  return Math.min(
    Math.max(Math.ceil((atMs - nowMs) / 1000), 0),
    MAX_RETRY_AFTER_SECONDS,
  );
}

export function createProviderRequestTracker(): ProviderRequestTracker {
  let providerRequests = 0;
  let inputTokens = 0;
  let outputTokens = 0;
  let totalTokens = 0;
  let hasUsage = false;
  let retryAfterSeconds: number | undefined;

  return {
    noteProviderRequest() {
      providerRequests = Math.min(providerRequests + 1, MAX_TRACKED_REQUESTS);
    },
    recordUsage(usage) {
      const normalized = normalizeTrackedUsage(usage);
      if (!normalized) return;
      hasUsage = true;
      inputTokens = Math.min(
        inputTokens + normalized.input_tokens,
        MAX_TRACKED_TOKENS,
      );
      outputTokens = Math.min(
        outputTokens + normalized.output_tokens,
        MAX_TRACKED_TOKENS,
      );
      totalTokens = Math.min(
        totalTokens + normalized.total_tokens,
        MAX_TRACKED_TOKENS,
      );
    },
    recordRetryAfter(value, nowMs = Date.now()) {
      if (value === null) return;
      const parsed = parseRetryAfterSeconds(value, nowMs);
      if (parsed === null) return;
      retryAfterSeconds = Math.max(retryAfterSeconds ?? 0, parsed);
    },
    snapshot() {
      return {
        provider_requests: providerRequests,
        ...(hasUsage
          ? {
              usage: {
                input_tokens: inputTokens,
                output_tokens: outputTokens,
                total_tokens: totalTokens,
              },
            }
          : {}),
        ...(retryAfterSeconds === undefined
          ? {}
          : { retry_after_seconds: retryAfterSeconds }),
      };
    },
  };
}

function isPlaceholder(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return (
    normalized.startsWith("your-") ||
    normalized.includes("placeholder") ||
    normalized.includes("replace-me") ||
    normalized === "changeme" ||
    normalized === "change-me"
  );
}

export function requireServerCredential(value: string | undefined): string {
  const trimmed = value?.trim() ?? "";
  if (!trimmed || isPlaceholder(trimmed)) {
    throw new ProviderRuntimeError("provider_auth_failed");
  }
  return trimmed;
}

function cloudflareBody(init: RequestInit | undefined): string | null {
  return typeof init?.body === "string" ? init.body : null;
}

function rewriteCloudflareNamedToolChoice(
  init: RequestInit | undefined,
): RequestInit | undefined {
  const body = cloudflareBody(init);
  if (body === null) return init;

  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    throw new ProviderRuntimeError("provider_unavailable");
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new ProviderRuntimeError("provider_unavailable");
  }

  const payload = parsed as Record<string, unknown>;
  const choice = payload.tool_choice;
  if (choice === undefined || typeof choice === "string") return init;
  if (typeof choice !== "object" || choice === null || Array.isArray(choice)) {
    throw new ProviderRuntimeError("provider_unavailable");
  }

  const choiceRecord = choice as Record<string, unknown>;
  const choiceFunction = choiceRecord.function;
  const selectedName =
    typeof choiceFunction === "object" && choiceFunction !== null
      ? (choiceFunction as Record<string, unknown>).name
      : null;
  const tools = payload.tools;
  if (!Array.isArray(tools) || tools.length !== 1) {
    throw new ProviderRuntimeError("provider_unavailable");
  }
  const onlyTool = tools[0];
  const onlyToolRecord =
    typeof onlyTool === "object" && onlyTool !== null
      ? (onlyTool as Record<string, unknown>)
      : null;
  const toolFunction =
    onlyToolRecord !== null ? onlyToolRecord.function : null;
  const onlyToolName =
    typeof toolFunction === "object" && toolFunction !== null
      ? (toolFunction as Record<string, unknown>).name
      : null;
  if (
    choiceRecord.type !== "function" ||
    selectedName !== "validateMove" ||
    onlyToolRecord?.type !== "function" ||
    onlyToolName !== "validateMove"
  ) {
    throw new ProviderRuntimeError("provider_unavailable");
  }

  return {
    ...init,
    body: JSON.stringify({ ...payload, tool_choice: "required" }),
  };
}

export function createTrackedProviderFetch(
  tracker: ProviderRequestTracker,
  options: { cloudflareNamedToolChoice?: boolean } = {},
): typeof globalThis.fetch {
  return async (input, init) => {
    const outgoingInit = options.cloudflareNamedToolChoice
      ? rewriteCloudflareNamedToolChoice(init)
      : init;
    tracker.noteProviderRequest();
    const response = await globalThis.fetch(input, outgoingInit);
    tracker.recordRetryAfter(response.headers.get("retry-after"));
    return response;
  };
}

function createTrackedOpenAIChatModel(input: {
  provider: string;
  modelId: string;
  baseURL: string;
  apiKey: string;
  tracker: ProviderRequestTracker;
  cloudflareNamedToolChoice?: boolean;
}): LanguageModel {
  const compatible = createOpenAI({
    baseURL: input.baseURL,
    apiKey: input.apiKey,
    name: input.provider,
    fetch: createTrackedProviderFetch(input.tracker, {
      cloudflareNamedToolChoice: input.cloudflareNamedToolChoice,
    }),
  });
  return compatible.chat(input.modelId);
}

const STANDARD_PAIR_CONFIG = {
  [GROQ_PROVIDER]: {
    modelId: GROQ_MODEL_ID,
    baseURL: "https://api.groq.com/openai/v1",
    credential: () => process.env.GROQ_API_KEY,
  },
  [GOOGLE_GEMINI_PROVIDER]: {
    modelId: GOOGLE_GEMINI_MODEL_ID,
    baseURL: "https://generativelanguage.googleapis.com/v1beta/openai",
    credential: () => process.env.GEMINI_API_KEY,
  },
  [MISTRAL_PROVIDER]: {
    modelId: MISTRAL_MODEL_ID,
    baseURL: "https://api.mistral.ai/v1",
    credential: () => process.env.MISTRAL_API_KEY,
  },
  [AION_PROVIDER]: {
    modelId: AION_MODEL_ID,
    baseURL: "https://api.aionlabs.ai/v1",
    credential: () => process.env.AION_API_KEY,
  },
  [HUGGINGFACE_PROVIDER]: {
    modelId: HUGGINGFACE_MODEL_ID,
    baseURL: "https://router.huggingface.co/v1",
    credential: () => process.env.HF_TOKEN,
  },
} as const;

type StandardPairProvider = keyof typeof STANDARD_PAIR_CONFIG;

function isStandardPairProvider(
  provider: string,
): provider is StandardPairProvider {
  return Object.prototype.hasOwnProperty.call(STANDARD_PAIR_CONFIG, provider);
}

function cloudflareBaseURL(): string {
  const accountId = requireServerCredential(process.env.CLOUDFLARE_ACCOUNT_ID);
  if (!/^[a-f\d]{32}$/i.test(accountId)) {
    throw new ProviderRuntimeError("provider_auth_failed");
  }
  return `https://api.cloudflare.com/client/v4/accounts/${accountId}/ai/v1`;
}

export function getStandardOpenAICompatibleModel(
  provider: string,
  modelId: string,
  tracker: ProviderRequestTracker,
): LanguageModel {
  if (provider === CLOUDFLARE_WORKERS_AI_PROVIDER) {
    if (modelId !== CLOUDFLARE_WORKERS_AI_MODEL_ID) {
      throw new ProviderRuntimeError("provider_unavailable");
    }
    const apiKey = requireServerCredential(process.env.CLOUDFLARE_API_TOKEN);
    return createTrackedOpenAIChatModel({
      provider,
      modelId,
      baseURL: cloudflareBaseURL(),
      apiKey,
      tracker,
      cloudflareNamedToolChoice: true,
    });
  }

  if (!isStandardPairProvider(provider)) {
    throw new ProviderRuntimeError("provider_unavailable");
  }
  const config = STANDARD_PAIR_CONFIG[provider];
  if (modelId !== config.modelId) {
    throw new ProviderRuntimeError("provider_unavailable");
  }
  return createTrackedOpenAIChatModel({
    provider,
    modelId,
    baseURL: config.baseURL,
    apiKey: requireServerCredential(config.credential()),
    tracker,
  });
}
