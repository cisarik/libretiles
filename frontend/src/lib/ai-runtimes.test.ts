import { generateText, type LanguageModel } from "ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import { __ibmWatsonxRuntimeTestOnly } from "./ibm-watsonx";
import {
  getLanguageRuntime,
  isLegalBackendTerminal,
  normalizeProviderError,
  revalidateRuntimePair,
} from "./ai-runtimes";
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
  IBM_WATSONX_MODEL_ID,
  IBM_WATSONX_PROVIDER,
  MISTRAL_MODEL_ID,
  MISTRAL_PROVIDER,
} from "./provider-registry";

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
  __ibmWatsonxRuntimeTestOnly.reset();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
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

function providerNotFoundError(message: string) {
  const lastError = Object.assign(new Error(message), {
    name: "AI_APICallError",
    statusCode: 404,
    responseBody: "secret-provider-response-sk-live-do-not-leak",
    responseHeaders: { authorization: "Bearer secret-key-value" },
  });
  return Object.assign(new Error("Provider request failed"), {
    name: "AI_RetryError",
    lastError,
    cause: { errors: [lastError] },
  });
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

function openAiChatResponse(modelId: string): Response {
  return new Response(
    JSON.stringify({
      id: "chatcmpl-test",
      object: "chat.completion",
      created: 1,
      model: modelId,
      choices: [
        {
          index: 0,
          message: { role: "assistant", content: "pong" },
          finish_reason: "stop",
        },
      ],
      usage: { prompt_tokens: 3, completion_tokens: 1, total_tokens: 4 },
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

describe("getLanguageRuntime", () => {
  it("uses every approved fixed base and bearer credential through Chat Completions", async () => {
    const cloudflareAccount = "0123456789abcdef0123456789abcdef";
    const cases = [
      {
        provider: GROQ_PROVIDER,
        modelId: GROQ_MODEL_ID,
        env: ["GROQ_API_KEY", "groq-test-secret"],
        url: "https://api.groq.com/openai/v1/chat/completions",
      },
      {
        provider: GOOGLE_GEMINI_PROVIDER,
        modelId: GOOGLE_GEMINI_MODEL_ID,
        env: ["GEMINI_API_KEY", "gemini-test-secret"],
        url: "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
      },
      {
        provider: CLOUDFLARE_WORKERS_AI_PROVIDER,
        modelId: CLOUDFLARE_WORKERS_AI_MODEL_ID,
        env: ["CLOUDFLARE_API_TOKEN", "cloudflare-test-secret"],
        url: `https://api.cloudflare.com/client/v4/accounts/${cloudflareAccount}/ai/v1/chat/completions`,
      },
      {
        provider: MISTRAL_PROVIDER,
        modelId: MISTRAL_MODEL_ID,
        env: ["MISTRAL_API_KEY", "mistral-test-secret"],
        url: "https://api.mistral.ai/v1/chat/completions",
      },
      {
        provider: AION_PROVIDER,
        modelId: AION_MODEL_ID,
        env: ["AION_API_KEY", "aion-test-secret"],
        url: "https://api.aionlabs.ai/v1/chat/completions",
      },
      {
        provider: HUGGINGFACE_PROVIDER,
        modelId: HUGGINGFACE_MODEL_ID,
        env: ["HF_TOKEN", "hf-test-secret"],
        url: "https://router.huggingface.co/v1/chat/completions",
      },
      {
        provider: "nvidia-nim",
        modelId: NVIDIA_NIM_NEMOTRON,
        env: ["NVIDIA_API_KEY", "nim-test-secret"],
        url: "https://integrate.api.nvidia.com/v1/chat/completions",
      },
      {
        provider: "openrouter",
        modelId: OPENROUTER_GEMMA,
        env: ["OPENROUTER_API_KEY", "openrouter-test-secret"],
        url: "https://openrouter.ai/api/v1/chat/completions",
      },
    ] as const;
    vi.stubEnv("CLOUDFLARE_ACCOUNT_ID", cloudflareAccount);

    for (const item of cases) {
      vi.stubEnv(item.env[0], item.env[1]);
      const fetchMock = vi.fn<
        (input: string | URL | Request, init?: RequestInit) => Promise<Response>
      >(async () => openAiChatResponse(item.modelId));
      vi.stubGlobal("fetch", fetchMock);
      const runtime = await getLanguageRuntime(item.provider, item.modelId);
      assertChatModel(runtime.model, item.provider, item.modelId);
      const generated = await generateText({
        model: runtime.model,
        prompt: "ping",
        maxRetries: 0,
      });
      expect(generated.text).toBe("pong");
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(item.url);
      expect(new Headers(init.headers).get("authorization")).toBe(
        `Bearer ${item.env[1]}`,
      );
      expect(runtime.tracker.snapshot().provider_requests).toBe(1);
      vi.unstubAllGlobals();
    }
  });

  it("dispatches the exact IBM pair through IAM before returning its chat model", async () => {
    vi.stubEnv("IBM_CLOUD_API_KEY", "ibm-test-api-key");
    vi.stubEnv("IBM_WATSONX_PROJECT_ID", "project-test-1234");
    vi.stubEnv("IBM_WATSONX_REGION", "eu-de");
    const fetchMock = vi.fn<
      (input: string | URL | Request, init?: RequestInit) => Promise<Response>
    >(async () =>
      Response.json({ access_token: "iam-test-token", expires_in: 3600 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const runtime = await getLanguageRuntime(
      IBM_WATSONX_PROVIDER,
      IBM_WATSONX_MODEL_ID,
    );
    assertChatModel(runtime.model, IBM_WATSONX_PROVIDER, IBM_WATSONX_MODEL_ID);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://iam.cloud.ibm.com/identity/token",
    );
    expect(runtime.tracker.snapshot().provider_requests).toBe(1);
  });

  it("throws sanitized auth errors and performs zero fetches for missing/placeholders", async () => {
    const cases = [
      [GROQ_PROVIDER, GROQ_MODEL_ID, "GROQ_API_KEY"],
      [GOOGLE_GEMINI_PROVIDER, GOOGLE_GEMINI_MODEL_ID, "GEMINI_API_KEY"],
      [MISTRAL_PROVIDER, MISTRAL_MODEL_ID, "MISTRAL_API_KEY"],
      [AION_PROVIDER, AION_MODEL_ID, "AION_API_KEY"],
      [HUGGINGFACE_PROVIDER, HUGGINGFACE_MODEL_ID, "HF_TOKEN"],
      ["nvidia-nim", NVIDIA_NIM_NEMOTRON, "NVIDIA_API_KEY"],
      ["openrouter", OPENROUTER_GEMMA, "OPENROUTER_API_KEY"],
    ] as const;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    for (const [provider, modelId, envName] of cases) {
      vi.stubEnv(envName, "your-provider-api-key");
      const promise = getLanguageRuntime(provider, modelId);
      await expect(promise).rejects.toMatchObject({
        code: "provider_auth_failed",
      });
      await expect(promise).rejects.not.toThrow(/API_KEY|your-provider/i);
    }
    vi.stubEnv("CLOUDFLARE_API_TOKEN", "your-cloudflare-api-token");
    vi.stubEnv(
      "CLOUDFLARE_ACCOUNT_ID",
      "0123456789abcdef0123456789abcdef",
    );
    await expect(
      getLanguageRuntime(
        CLOUDFLARE_WORKERS_AI_PROVIDER,
        CLOUDFLARE_WORKERS_AI_MODEL_ID,
      ),
    ).rejects.toMatchObject({ code: "provider_auth_failed" });
    vi.stubEnv("CLOUDFLARE_API_TOKEN", "cloudflare-test-secret");
    vi.stubEnv("CLOUDFLARE_ACCOUNT_ID", "not-an-account-id");
    await expect(
      getLanguageRuntime(
        CLOUDFLARE_WORKERS_AI_PROVIDER,
        CLOUDFLARE_WORKERS_AI_MODEL_ID,
      ),
    ).rejects.toMatchObject({ code: "provider_auth_failed" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects paid, unknown-provider, cross-provider, and non-free pairs before fetch", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const invalid = [
      ["openrouter", "openai/gpt-5-mini"],
      ["anthropic", "anthropic/claude:free"],
      ["openrouter", NVIDIA_NIM_NEMOTRON],
      ["nvidia-nim", OPENROUTER_GEMMA],
      ["openrouter", "openrouter/free"],
      [GROQ_PROVIDER, GOOGLE_GEMINI_MODEL_ID],
    ] as const;
    for (const [provider, modelId] of invalid) {
      await expect(getLanguageRuntime(provider, modelId)).rejects.toThrow(
        /unknown free-rival pair/i,
      );
    }
    expect(fetchMock).not.toHaveBeenCalled();
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

  it("classifies nested AI SDK 404 endpoint failures without leaking provider text", () => {
    const classified = normalizeProviderError(
      providerNotFoundError("No endpoints found for stealth/example:free"),
    );
    expect(classified).toEqual({
      code: "provider_unavailable",
      message:
        "This free rival is temporarily unavailable. Switch to another free rival or retry later.",
    });
    expect(JSON.stringify(classified)).not.toContain("stealth/example:free");
    expect(JSON.stringify(classified)).not.toContain("No endpoints found");
    expect(JSON.stringify(classified)).not.toContain("sk-live");
    expect(JSON.stringify(classified)).not.toContain("secret-key-value");
  });

  it("classifies the official no-allowed-providers wording without wrapper status", () => {
    expect(
      normalizeProviderError(
        new Error(
          "No allowed providers are available for the selected model",
        ),
      ),
    ).toEqual({
      code: "provider_unavailable",
      message:
        "This free rival is temporarily unavailable. Switch to another free rival or retry later.",
    });
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
    expect(
      normalizeProviderError({ statusCode: 403, message: "nope" })?.code,
    ).toBe("provider_auth_failed");
    expect(
      normalizeProviderError({ statusCode: 408, message: "nope" })?.code,
    ).toBe("provider_unavailable");
  });

  it("classifies quota, overload, model capacity, and unsupported-tools", () => {
    expect(
      normalizeProviderError(new Error("RESOURCE_EXHAUSTED"))?.code,
    ).toBe("provider_rate_limited");
    expect(
      normalizeProviderError(new Error("The model is overloaded"))?.code,
    ).toBe("provider_unavailable");
    expect(
      normalizeProviderError(new Error("The deployment has no capacity"))?.code,
    ).toBe("provider_unavailable");
    expect(
      normalizeProviderError(new Error("model is unavailable"))?.code,
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

  it("does not classify arbitrary application 404 or plain model-not-found errors", () => {
    expect(
      normalizeProviderError({
        statusCode: 404,
        message: "Django page not found",
      }),
    ).toBeNull();
    expect(normalizeProviderError(new Error("model not found"))).toBeNull();
  });

  it("preserves auth and rate-limit precedence over endpoint unavailability", () => {
    expect(
      normalizeProviderError({
        statusCode: 429,
        message: "No endpoints found",
      })?.code,
    ).toBe("provider_rate_limited");
    expect(
      normalizeProviderError({
        statusCode: 429,
        message: "No endpoints found",
        cause: { statusCode: 401, message: "invalid API key" },
      })?.code,
    ).toBe("provider_auth_failed");
  });

  it("walks cyclic graphs without throwing", () => {
    const cyclic: { cause?: unknown; statusCode: number } = {
      statusCode: 429,
    };
    cyclic.cause = cyclic;
    expect(normalizeProviderError(cyclic)?.code).toBe("provider_rate_limited");
  });
});
