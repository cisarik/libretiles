/**
 * Client-safe metadata for every Libre Tiles AI runtime pair.
 *
 * This module is safe to import from browser code: it deliberately contains
 * no environment-variable access, credentials, provider base URLs, or
 * account-specific values. Runtime construction remains server-only in
 * `ai-runtimes.ts`.
 */

export const OPENROUTER_PROVIDER = "openrouter" as const;
export const NVIDIA_NIM_PROVIDER = "nvidia-nim" as const;
export const GROQ_PROVIDER = "groq" as const;
export const GOOGLE_GEMINI_PROVIDER = "google-gemini" as const;
export const CLOUDFLARE_WORKERS_AI_PROVIDER =
  "cloudflare-workers-ai" as const;
export const MISTRAL_PROVIDER = "mistral" as const;
export const IBM_WATSONX_PROVIDER = "ibm-watsonx" as const;
export const AION_PROVIDER = "aion" as const;
export const HUGGINGFACE_PROVIDER = "huggingface" as const;

export const NVIDIA_NIM_MODEL_ID =
  "nvidia/nemotron-3-super-120b-a12b" as const;
export const GROQ_MODEL_ID = "openai/gpt-oss-120b" as const;
export const GOOGLE_GEMINI_MODEL_ID = "gemini-3.7-flash" as const;
export const CLOUDFLARE_WORKERS_AI_MODEL_ID =
  "@cf/zai-org/glm-4.7-flash" as const;
export const MISTRAL_MODEL_ID = "mistral-small-2603" as const;
export const IBM_WATSONX_MODEL_ID = "ibm/granite-4-h-small" as const;
export const AION_MODEL_ID = "aion-labs/aion-3.0-mini" as const;
export const HUGGINGFACE_MODEL_ID = "openai/gpt-oss-120b:groq" as const;

export type ProviderCatalogTier = "direct" | "watchlist" | "legacy";
export type ProviderRuntimeKind =
  | "openai-compatible"
  | "ibm-watsonx-pending";

export type ExactProviderMetadata = Readonly<{
  provider: string;
  model_id: string;
  provider_label: string;
  model_label: string;
  catalog_tier: ProviderCatalogTier;
  runtime_kind: ProviderRuntimeKind;
}>;

/**
 * Exact tuples are intentionally duplicated from the backend catalog boundary.
 * A tuple must match here and in the live Django catalog before a route may use
 * it. IBM is structurally known but its server runtime lands in the next slice.
 */
export const EXACT_PROVIDER_METADATA = [
  {
    provider: GROQ_PROVIDER,
    model_id: GROQ_MODEL_ID,
    provider_label: "Groq",
    model_label: "GPT-OSS 120B",
    catalog_tier: "direct",
    runtime_kind: "openai-compatible",
  },
  {
    provider: GOOGLE_GEMINI_PROVIDER,
    model_id: GOOGLE_GEMINI_MODEL_ID,
    provider_label: "Google Gemini",
    model_label: "Gemini 3.7 Flash",
    catalog_tier: "direct",
    runtime_kind: "openai-compatible",
  },
  {
    provider: CLOUDFLARE_WORKERS_AI_PROVIDER,
    model_id: CLOUDFLARE_WORKERS_AI_MODEL_ID,
    provider_label: "Cloudflare Workers AI",
    model_label: "GLM 4.7 Flash",
    catalog_tier: "direct",
    runtime_kind: "openai-compatible",
  },
  {
    provider: MISTRAL_PROVIDER,
    model_id: MISTRAL_MODEL_ID,
    provider_label: "Mistral",
    model_label: "Mistral Small 2603",
    catalog_tier: "direct",
    runtime_kind: "openai-compatible",
  },
  {
    provider: IBM_WATSONX_PROVIDER,
    model_id: IBM_WATSONX_MODEL_ID,
    provider_label: "IBM watsonx.ai",
    model_label: "Granite 4 H Small",
    catalog_tier: "direct",
    runtime_kind: "ibm-watsonx-pending",
  },
  {
    provider: AION_PROVIDER,
    model_id: AION_MODEL_ID,
    provider_label: "Aion",
    model_label: "Aion 3.0 Mini",
    catalog_tier: "watchlist",
    runtime_kind: "openai-compatible",
  },
  {
    provider: HUGGINGFACE_PROVIDER,
    model_id: HUGGINGFACE_MODEL_ID,
    provider_label: "Hugging Face",
    model_label: "GPT-OSS 120B",
    catalog_tier: "watchlist",
    runtime_kind: "openai-compatible",
  },
  {
    provider: NVIDIA_NIM_PROVIDER,
    model_id: NVIDIA_NIM_MODEL_ID,
    provider_label: "NVIDIA NIM",
    model_label: "Nemotron 3 Super 120B",
    catalog_tier: "legacy",
    runtime_kind: "openai-compatible",
  },
] as const satisfies readonly ExactProviderMetadata[];

export type ExactRuntimeProvider =
  (typeof EXACT_PROVIDER_METADATA)[number]["provider"];
export type AiRuntimeProvider =
  | typeof OPENROUTER_PROVIDER
  | ExactRuntimeProvider;

/** Backend selection excludes this OpenRouter meta-row explicitly. */
const EXCLUDED_OPENROUTER_IDS: ReadonlySet<string> = new Set([
  "openrouter/free",
]);

export function isOpenRouterFreeId(modelId: string): boolean {
  if (!modelId.includes("/")) return false;
  if (!modelId.endsWith(":free")) return false;
  return !EXCLUDED_OPENROUTER_IDS.has(modelId);
}

export function findExactProviderMetadata(
  provider: string,
  modelId: string,
): ExactProviderMetadata | null {
  return (
    EXACT_PROVIDER_METADATA.find(
      (entry) => entry.provider === provider && entry.model_id === modelId,
    ) ?? null
  );
}

export function isKnownProvider(provider: string): provider is AiRuntimeProvider {
  return (
    provider === OPENROUTER_PROVIDER ||
    EXACT_PROVIDER_METADATA.some((entry) => entry.provider === provider)
  );
}

/**
 * Structural validation only. Route handlers must additionally revalidate the
 * same tuple against the live Django catalog before runtime construction.
 */
export function isValidRuntimePair(provider: string, modelId: string): boolean {
  if (provider === OPENROUTER_PROVIDER) return isOpenRouterFreeId(modelId);
  return findExactProviderMetadata(provider, modelId) !== null;
}

export function providerLabel(provider: string): string {
  if (provider === OPENROUTER_PROVIDER) return "OpenRouter";
  return (
    EXACT_PROVIDER_METADATA.find((entry) => entry.provider === provider)
      ?.provider_label ?? provider
  );
}
