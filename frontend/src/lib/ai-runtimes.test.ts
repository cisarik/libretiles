import type { LanguageModel } from "ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getLanguageModel,
  isLegalBackendTerminal,
  normalizeProviderError,
  revalidateRuntimePair,
} from "./ai-runtimes";

const OPENROUTER_GEMMA = "google/gemma-4-31b-it:free";
const NVIDIA_NIM_NEMOTRON = "nvidia/nemotron-3-super-120b-a12b";
const OPENROUTER_NEMOTRON = "nvidia/nemotron-3-super-120b-a12b:free";

const CATALOG_ROWS = [
  { provider: "openrouter", model_id: OPENROUTER_GEMMA },
  { provider: "nvidia-nim", model_id: NVIDIA_NIM_NEMOTRON },
  { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
  { provider: "openrouter", model_id: "z-ai/glm-5.2:free" },
];

afterEach(() => {
  vi.unstubAllEnvs();
});

function retryErrorWithStatus(statusCode: number) {
  const lastError = {
    name: "AI_APICallError",
    message: "Provider returned error",
    statusCode,
    responseBody: `secret-body-sk-live-do-not-leak status ${statusCode}`,
    responseHeaders: { authorization: "Bearer secret-key-value" },
  };
  return Object.assign(
    new Error("Failed after 3 attempts. Last error: Provider returned error"),
    {
      name: "AI_RetryError",
      lastError,
      errors: [lastError, lastError, lastError],
    },
  );
}

function assertChatModel(
  model: LanguageModel,
  providerNeedle: string,
  modelId: string,
) {
  expect(model).not.toBeTypeOf("string");
  if (typeof model === "string") return;
  expect(model.provider).toContain(providerNeedle);
  expect(model.modelId).toBe(modelId);
}

describe("getLanguageModel", () => {
  it("maps catalog-confirmed OpenRouter :free IDs through Chat Completions", () => {
    vi.stubEnv("OPENROUTER_API_KEY", "test-openrouter-key");
    const model = getLanguageModel("openrouter", OPENROUTER_GEMMA);
    assertChatModel(model, "openrouter", OPENROUTER_GEMMA);
    const nemotron = getLanguageModel("openrouter", OPENROUTER_NEMOTRON);
    assertChatModel(nemotron, "openrouter", OPENROUTER_NEMOTRON);
  });

  it("maps the fixed NVIDIA NIM tuple through Chat Completions", () => {
    vi.stubEnv("NVIDIA_API_KEY", "test-nvidia-key");
    const model = getLanguageModel("nvidia-nim", NVIDIA_NIM_NEMOTRON);
    assertChatModel(model, "nvidia-nim", NVIDIA_NIM_NEMOTRON);
  });

  it("throws a sanitised auth error when the NVIDIA key is missing", () => {
    vi.stubEnv("NVIDIA_API_KEY", "");
    const secret = "nvapi-super-secret-value";
    expect(() => getLanguageModel("nvidia-nim", NVIDIA_NIM_NEMOTRON)).toThrow(
      /authentication failed/i,
    );
    try {
      getLanguageModel("nvidia-nim", NVIDIA_NIM_NEMOTRON);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      expect(message).not.toContain(secret);
      expect(message).not.toMatch(/nvapi-/i);
      expect(message.toLowerCase()).not.toContain("nvidia_api_key=");
    }
  });

  it("rejects paid, unknown-provider, cross-provider, and non-free pairs", () => {
    vi.stubEnv("OPENROUTER_API_KEY", "test-openrouter-key");
    vi.stubEnv("NVIDIA_API_KEY", "test-nvidia-key");
    // OpenRouter runtime ID without the :free suffix
    expect(() =>
      getLanguageModel("openrouter", "openai/gpt-5-mini"),
    ).toThrow(/unknown free-rival pair/i);
    // Unknown provider
    expect(() =>
      getLanguageModel("anthropic", "anthropic/claude:free"),
    ).toThrow(/unknown free-rival pair/i);
    // NIM tuple claimed under the OpenRouter provider
    expect(() =>
      getLanguageModel("openrouter", NVIDIA_NIM_NEMOTRON),
    ).toThrow(/unknown free-rival pair/i);
    // OpenRouter :free id claimed under the NIM provider
    expect(() =>
      getLanguageModel("nvidia-nim", OPENROUTER_GEMMA),
    ).toThrow(/unknown free-rival pair/i);
    // Excluded meta-row
    expect(() =>
      getLanguageModel("openrouter", "openrouter/free"),
    ).toThrow(/unknown free-rival pair/i);
  });
});

describe("revalidateRuntimePair", () => {
  it("accepts only exact structurally valid pairs that are in the catalog", () => {
    expect(
      revalidateRuntimePair("nvidia-nim", NVIDIA_NIM_NEMOTRON, CATALOG_ROWS),
    ).toBe(true);
    expect(
      revalidateRuntimePair("openrouter", OPENROUTER_GEMMA, CATALOG_ROWS),
    ).toBe(true);
    // Structurally valid but absent from the catalog
    expect(
      revalidateRuntimePair("openrouter", "qwen/qwen3-next:free", CATALOG_ROWS),
    ).toBe(false);
    expect(
      revalidateRuntimePair("nvidia-nim", NVIDIA_NIM_NEMOTRON, [
        { provider: "openrouter", model_id: OPENROUTER_GEMMA },
      ]),
    ).toBe(false);
    // Structurally invalid even when present
    expect(
      revalidateRuntimePair("openrouter", NVIDIA_NIM_NEMOTRON, [
        { provider: "openrouter", model_id: NVIDIA_NIM_NEMOTRON },
      ]),
    ).toBe(false);
    expect(
      revalidateRuntimePair("openrouter", "openai/gpt-5-mini", [
        { provider: "openrouter", model_id: "openai/gpt-5-mini" },
      ]),
    ).toBe(false);
  });
});

describe("isLegalBackendTerminal", () => {
  it("is true only for ok:true place/pass/exchange payloads", () => {
    expect(isLegalBackendTerminal({ ok: true, action: "place" })).toBe(true);
    expect(isLegalBackendTerminal({ ok: true, action: "pass" })).toBe(true);
    expect(isLegalBackendTerminal({ ok: true, action: "exchange" })).toBe(true);
  });

  it("rejects failed pass/exchange payloads so routes must not emit done", () => {
    expect(isLegalBackendTerminal({ ok: false, action: "pass" })).toBe(false);
    expect(isLegalBackendTerminal({ ok: false, action: "exchange" })).toBe(
      false,
    );
    expect(isLegalBackendTerminal({ action: "pass" })).toBe(false);
    expect(isLegalBackendTerminal(null)).toBe(false);
    expect(isLegalBackendTerminal("ok")).toBe(false);
    expect(isLegalBackendTerminal({ ok: true, action: "pass" })).toBe(true);
  });
});

describe("normalizeProviderError", () => {
  it("classifies a nested RetryError 429 without leaking bodies or keys", () => {
    const classified = normalizeProviderError(retryErrorWithStatus(429));
    expect(classified?.code).toBe("provider_rate_limited");
    expect(classified?.message).not.toContain("secret-body");
    expect(classified?.message).not.toContain("secret-key-value");
    expect(classified?.message).not.toContain("Bearer");
    expect(classified?.message).not.toMatch(/sk-live/);
  });

  it("classifies nested 401 as provider_auth_failed", () => {
    expect(normalizeProviderError(retryErrorWithStatus(401))?.code).toBe(
      "provider_auth_failed",
    );
  });

  it("classifies nested 503 as provider_unavailable", () => {
    expect(normalizeProviderError(retryErrorWithStatus(503))?.code).toBe(
      "provider_unavailable",
    );
  });

  it("classifies direct statusCode values", () => {
    expect(
      normalizeProviderError({ statusCode: 401, message: "nope" })?.code,
    ).toBe("provider_auth_failed");
    expect(
      normalizeProviderError({ statusCode: 429, message: "nope" })?.code,
    ).toBe("provider_rate_limited");
    expect(
      normalizeProviderError({ status: 502, message: "nope" })?.code,
    ).toBe("provider_unavailable");
    expect(
      normalizeProviderError({ statusCode: 504, message: "nope" })?.code,
    ).toBe("provider_unavailable");
  });

  it("classifies overload and unsupported-tools as provider_unavailable", () => {
    expect(
      normalizeProviderError(new Error("The model is overloaded"))?.code,
    ).toBe("provider_unavailable");
    expect(
      normalizeProviderError(new Error("unsupported tool calling"))?.code,
    ).toBe("provider_unavailable");
  });

  it("returns null for unknown errors and never copies raw bodies", () => {
    const raw = {
      message: "something else",
      responseBody: "sk-live-raw-body",
    };
    expect(normalizeProviderError(raw)).toBeNull();
  });

  it("walks cyclic graphs without throwing", () => {
    const cyclic: { cause?: unknown; statusCode: number } = {
      statusCode: 429,
    };
    cyclic.cause = cyclic;
    expect(normalizeProviderError(cyclic)?.code).toBe("provider_rate_limited");
  });
});
