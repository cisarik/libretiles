import { describe, expect, it } from "vitest";
import {
  AION_MODEL_ID,
  AION_PROVIDER,
  CLOUDFLARE_WORKERS_AI_MODEL_ID,
  CLOUDFLARE_WORKERS_AI_PROVIDER,
  EXACT_PROVIDER_METADATA,
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
  findExactProviderMetadata,
  isOpenRouterFreeId,
  isValidRuntimePair,
  providerLabel,
} from "./provider-registry";

const EXACT_PAIRS = [
  [GROQ_PROVIDER, GROQ_MODEL_ID],
  [GOOGLE_GEMINI_PROVIDER, GOOGLE_GEMINI_MODEL_ID],
  [CLOUDFLARE_WORKERS_AI_PROVIDER, CLOUDFLARE_WORKERS_AI_MODEL_ID],
  [MISTRAL_PROVIDER, MISTRAL_MODEL_ID],
  [IBM_WATSONX_PROVIDER, IBM_WATSONX_MODEL_ID],
  [AION_PROVIDER, AION_MODEL_ID],
  [HUGGINGFACE_PROVIDER, HUGGINGFACE_MODEL_ID],
  [NVIDIA_NIM_PROVIDER, NVIDIA_NIM_MODEL_ID],
] as const;

describe("client-safe provider registry", () => {
  it("contains every approved exact direct, watchlist, and NIM tuple", () => {
    expect(EXACT_PROVIDER_METADATA).toHaveLength(EXACT_PAIRS.length);
    for (const [provider, modelId] of EXACT_PAIRS) {
      expect(findExactProviderMetadata(provider, modelId)).toMatchObject({
        provider,
        model_id: modelId,
      });
      expect(isValidRuntimePair(provider, modelId)).toBe(true);
    }
  });

  it("rejects cross-provider, arbitrary, paid, and meta-row pairs", () => {
    expect(isValidRuntimePair(GROQ_PROVIDER, GOOGLE_GEMINI_MODEL_ID)).toBe(false);
    expect(isValidRuntimePair(MISTRAL_PROVIDER, "mistral-small-latest")).toBe(false);
    expect(isValidRuntimePair("openai", "gpt-5-mini")).toBe(false);
    expect(isValidRuntimePair(OPENROUTER_PROVIDER, "openai/gpt-5-mini")).toBe(
      false,
    );
    expect(isValidRuntimePair(OPENROUTER_PROVIDER, "openrouter/free")).toBe(
      false,
    );
  });

  it("keeps OpenRouter structural support limited to native :free ids", () => {
    expect(isOpenRouterFreeId("google/gemma-4-31b-it:free")).toBe(true);
    expect(isOpenRouterFreeId("vendor/model")).toBe(false);
    expect(isOpenRouterFreeId(":free")).toBe(false);
  });

  it("exposes human labels without any server configuration metadata", () => {
    expect(providerLabel(CLOUDFLARE_WORKERS_AI_PROVIDER)).toBe(
      "Cloudflare Workers AI",
    );
    expect(providerLabel(OPENROUTER_PROVIDER)).toBe("OpenRouter");
    const serialized = JSON.stringify(EXACT_PROVIDER_METADATA).toLowerCase();
    expect(serialized).not.toContain("api_key");
    expect(serialized).not.toContain("token");
    expect(serialized).not.toContain("https://");
    expect(serialized).not.toContain("account_id");
  });
});
