import { describe, expect, it } from "vitest";
import {
  NVIDIA_NIM_MODEL_ID,
  NVIDIA_NIM_PROVIDER,
  OPENROUTER_PROVIDER,
  findCatalogPair,
  isOpenRouterFreeId,
  isValidRuntimePair,
  playableCatalogPairs,
  revalidateRuntimePair,
  resolveEligibleModelId,
} from "./model-catalog";

const OPENROUTER_GEMMA = "google/gemma-4-31b-it:free";
const OPENROUTER_GLM = "z-ai/glm-5.2:free";

describe("isOpenRouterFreeId", () => {
  it("accepts native vendor/model:free identifiers", () => {
    expect(isOpenRouterFreeId(OPENROUTER_GEMMA)).toBe(true);
    expect(isOpenRouterFreeId(OPENROUTER_GLM)).toBe(true);
  });

  it("rejects paid ids without the :free suffix", () => {
    expect(isOpenRouterFreeId("openai/gpt-5-mini")).toBe(false);
    expect(isOpenRouterFreeId(NVIDIA_NIM_MODEL_ID)).toBe(false);
    expect(isOpenRouterFreeId("gemma-free")).toBe(false);
    expect(isOpenRouterFreeId(":free")).toBe(false);
  });

  it("rejects the excluded meta-row", () => {
    expect(isOpenRouterFreeId("openrouter/free")).toBe(false);
  });
});

describe("isValidRuntimePair", () => {
  it("binds OpenRouter to :free shapes and NIM to its fixed tuple", () => {
    expect(isValidRuntimePair(OPENROUTER_PROVIDER, OPENROUTER_GEMMA)).toBe(true);
    expect(isValidRuntimePair(OPENROUTER_PROVIDER, "openai/gpt-5-mini")).toBe(false);
    expect(
      isValidRuntimePair(NVIDIA_NIM_PROVIDER, NVIDIA_NIM_MODEL_ID),
    ).toBe(true);
    expect(
      isValidRuntimePair(NVIDIA_NIM_PROVIDER, `${NVIDIA_NIM_MODEL_ID}:free`),
    ).toBe(false);
    expect(
      isValidRuntimePair(OPENROUTER_PROVIDER, NVIDIA_NIM_MODEL_ID),
    ).toBe(false);
  });

  it("rejects unknown providers entirely", () => {
    expect(isValidRuntimePair("anthropic", "anthropic/claude:free")).toBe(false);
    expect(isValidRuntimePair("", OPENROUTER_GEMMA)).toBe(false);
  });
});

describe("playableCatalogPairs / findCatalogPair", () => {
  const rows = [
    { provider: OPENROUTER_PROVIDER, model_id: OPENROUTER_GLM },
    { provider: OPENROUTER_PROVIDER, model_id: "openai/gpt-5-mini" }, // paid
    { provider: "anthropic", model_id: "anthropic/claude:free" }, // unknown provider
    { provider: NVIDIA_NIM_PROVIDER, model_id: NVIDIA_NIM_MODEL_ID },
  ];

  it("fails closed on paid, unknown-provider, and malformed rows", () => {
    expect(playableCatalogPairs(rows)).toEqual([
      { provider: OPENROUTER_PROVIDER, model_id: OPENROUTER_GLM },
      { provider: NVIDIA_NIM_PROVIDER, model_id: NVIDIA_NIM_MODEL_ID },
    ]);
    expect(playableCatalogPairs([{ provider: 3 } as never])).toEqual([]);
    expect(playableCatalogPairs([])).toEqual([]);
  });

  it("finds an exact playable pair or returns null", () => {
    expect(findCatalogPair(OPENROUTER_GLM, rows)).toEqual({
      provider: OPENROUTER_PROVIDER,
      model_id: OPENROUTER_GLM,
    });
    expect(findCatalogPair("openai/gpt-5-mini", rows)).toBeNull();
    expect(findCatalogPair(null, rows)).toBeNull();
    expect(findCatalogPair(undefined, [])).toBeNull();
  });
});

describe("revalidateRuntimePair", () => {
  it("requires both structural validity and catalog confirmation", () => {
    const rows = [{ provider: OPENROUTER_PROVIDER, model_id: OPENROUTER_GEMMA }];
    expect(revalidateRuntimePair(OPENROUTER_PROVIDER, OPENROUTER_GEMMA, rows)).toBe(true);
    expect(
      revalidateRuntimePair(OPENROUTER_PROVIDER, OPENROUTER_GLM, rows),
    ).toBe(false);
    expect(revalidateRuntimePair("openrouter", "openai/gpt-5-mini", [
      { provider: "openrouter", model_id: "openai/gpt-5-mini" },
    ])).toBe(false);
  });
});

describe("resolveEligibleModelId", () => {
  const eligibleIds = [OPENROUTER_GLM, OPENROUTER_GEMMA];

  it("prefers a valid server preference", () => {
    expect(resolveEligibleModelId(eligibleIds, OPENROUTER_GEMMA, null)).toBe(
      OPENROUTER_GEMMA,
    );
  });

  it("falls back to a valid stored selection before catalog row 1", () => {
    expect(
      resolveEligibleModelId(eligibleIds, "stale/model:free", OPENROUTER_GEMMA),
    ).toBe(OPENROUTER_GEMMA);
  });

  it("defaults new users with no preference to catalog row 1 (newest)", () => {
    expect(resolveEligibleModelId(eligibleIds, "", "")).toBe(OPENROUTER_GLM);
    expect(resolveEligibleModelId(eligibleIds, null, undefined)).toBe(
      OPENROUTER_GLM,
    );
  });

  it("returns null only for an empty catalog", () => {
    expect(resolveEligibleModelId([], OPENROUTER_GEMMA, OPENROUTER_GLM)).toBeNull();
  });
});
