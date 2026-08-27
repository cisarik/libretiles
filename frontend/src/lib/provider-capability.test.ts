import type { LanguageModel } from "ai";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  createProviderRequestTracker,
  type ProviderRequestTracker,
} from "./openai-compatible";
import {
  GROQ_MODEL_ID,
  GROQ_PROVIDER,
  IBM_WATSONX_MODEL_ID,
  IBM_WATSONX_PROVIDER,
  OPENROUTER_PROVIDER,
} from "./provider-registry";

const mocks = vi.hoisted(() => ({
  generateText: vi.fn(),
  getLanguageRuntime: vi.fn(),
}));

vi.mock("ai", async (importOriginal) => {
  const actual = await importOriginal<typeof import("ai")>();
  return { ...actual, generateText: mocks.generateText };
});

vi.mock("./ai-runtimes", () => ({
  getLanguageRuntime: mocks.getLanguageRuntime,
}));

import {
  PROVIDER_CAPABILITY_PLACEMENTS,
  PROVIDER_CAPABILITY_STATUSES,
  probeProviderCapability,
} from "./provider-capability";

type ValidateInput = {
  placements: Array<{ row: number; col: number; letter: string }>;
};

type ProbeGenerationOptions = {
  maxRetries: number;
  abortSignal: AbortSignal;
  tools: {
    validateMove: {
      execute: (input: ValidateInput) => Promise<unknown>;
    };
    finishMove: {
      execute: (input: { ready: boolean }) => Promise<unknown>;
    };
  };
  prepareStep: (input: { stepNumber: number }) => Record<string, unknown>;
  stopWhen: (input: { steps: unknown[] }) => boolean;
  onStepFinish: (step: {
    toolCalls: Array<{
      dynamic?: boolean;
      invalid?: boolean;
      error?: unknown;
    }>;
    content: Array<{ type: string; error?: unknown }>;
  }) => void;
};

let tracker: ProviderRequestTracker;

function generationOptions(raw: unknown): ProbeGenerationOptions {
  return raw as ProbeGenerationOptions;
}

function apiError(
  statusCode: number,
  message: string,
  code?: string,
): Error {
  return Object.assign(new Error(message), {
    name: "AI_APICallError",
    statusCode,
    ...(code ? { code } : {}),
    responseBody: "raw-secret-body-sk-never-serialize",
    responseHeaders: { authorization: "Bearer fake-secret" },
    reasoning: "private-chain-of-thought",
  });
}

beforeEach(() => {
  mocks.generateText.mockReset();
  mocks.getLanguageRuntime.mockReset();
  tracker = createProviderRequestTracker();
  mocks.getLanguageRuntime.mockResolvedValue({
    model: {} as LanguageModel,
    tracker,
  });
  vi.stubGlobal("crypto", { randomUUID: () => "probe-nonce-123" });
});

describe("provider capability probe", () => {
  it("performs the exact named validate -> pong -> auto finish state machine", async () => {
    let validateResult: unknown;
    let firstStep: Record<string, unknown> | undefined;
    let continuation: Record<string, unknown> | undefined;
    let maxThreeStops = false;

    mocks.generateText.mockImplementation(async (raw: unknown) => {
      const options = generationOptions(raw);
      tracker.noteProviderRequest();
      firstStep = options.prepareStep({ stepNumber: 0 });
      validateResult = await options.tools.validateMove.execute({
        placements: PROVIDER_CAPABILITY_PLACEMENTS.map((placement) => ({
          ...placement,
        })),
      });
      tracker.noteProviderRequest();
      continuation = options.prepareStep({ stepNumber: 1 });
      maxThreeStops =
        !options.stopWhen({ steps: [{}, {}] }) &&
        options.stopWhen({ steps: [{}, {}, {}] });
      await options.tools.finishMove.execute({ ready: true });
      return {
        usage: { inputTokens: 1, outputTokens: 1, totalTokens: 2 },
        totalUsage: { inputTokens: 9, outputTokens: 3, totalTokens: 12 },
      };
    });

    const result = await probeProviderCapability({ provider: GROQ_PROVIDER });

    expect(mocks.getLanguageRuntime).toHaveBeenCalledWith(
      GROQ_PROVIDER,
      GROQ_MODEL_ID,
    );
    expect(validateResult).toEqual({
      valid: true,
      nonce: "probe-nonce-123",
    });
    expect(firstStep).toEqual({
      activeTools: ["validateMove"],
      toolChoice: { type: "tool", toolName: "validateMove" },
    });
    expect(continuation).toEqual({
      activeTools: ["validateMove", "finishMove"],
      toolChoice: "auto",
    });
    expect(maxThreeStops).toBe(true);
    expect(generationOptions(mocks.generateText.mock.calls[0][0]).maxRetries).toBe(
      0,
    );
    expect(result).toEqual({
      provider: GROQ_PROVIDER,
      model: GROQ_MODEL_ID,
      status: "pass",
      latency_ms: expect.any(Number),
      outbound_count: 2,
    });
    expect(Object.keys(result)).toEqual([
      "provider",
      "model",
      "status",
      "latency_ms",
      "outbound_count",
    ]);
    expect(tracker.snapshot().usage).toEqual({
      input_tokens: 9,
      output_tokens: 3,
      total_tokens: 12,
    });
  });

  it("counts every tracker request, including simulated IBM IAM", async () => {
    mocks.generateText.mockImplementation(async (raw: unknown) => {
      const options = generationOptions(raw);
      tracker.noteProviderRequest(); // IAM
      tracker.noteProviderRequest(); // validate generation
      await options.tools.validateMove.execute({
        placements: PROVIDER_CAPABILITY_PLACEMENTS.map((item) => ({ ...item })),
      });
      tracker.noteProviderRequest(); // finish generation
      await options.tools.finishMove.execute({ ready: true });
      return { usage: { inputTokens: 2, outputTokens: 1, totalTokens: 3 } };
    });

    const result = await probeProviderCapability({
      provider: IBM_WATSONX_PROVIDER,
      model: IBM_WATSONX_MODEL_ID,
    });

    expect(result.status).toBe("pass");
    expect(result.outbound_count).toBe(3);
  });

  it("fails missing, spoofed, and model-less OpenRouter choices locally", async () => {
    const missing = await probeProviderCapability({});
    const spoofed = await probeProviderCapability({
      provider: GROQ_PROVIDER,
      model: "attacker/model",
    });
    const openRouter = await probeProviderCapability({
      provider: OPENROUTER_PROVIDER,
    });

    expect(missing).toMatchObject({
      provider: "not_configured",
      model: "not_configured",
      status: "not_configured",
      outbound_count: 0,
    });
    expect(spoofed).toMatchObject({
      provider: GROQ_PROVIDER,
      model: "invalid",
      status: "not_configured",
      outbound_count: 0,
    });
    expect(openRouter).toMatchObject({
      provider: OPENROUTER_PROVIDER,
      model: "not_configured",
      status: "not_configured",
      outbound_count: 0,
    });
    expect(mocks.getLanguageRuntime).not.toHaveBeenCalled();
  });

  it("maps a pre-network placeholder credential to not_configured", async () => {
    mocks.getLanguageRuntime.mockRejectedValue(
      Object.assign(new Error("fake-secret must not escape"), {
        name: "ProviderRuntimeError",
        code: "provider_auth_failed",
      }),
    );

    const result = await probeProviderCapability({ provider: GROQ_PROVIDER });

    expect(result).toMatchObject({
      status: "not_configured",
      outbound_count: 0,
    });
    expect(JSON.stringify(result)).not.toContain("fake-secret");
  });

  it.each([
    ["auth_failed", 401, "unauthorized fake-secret"],
    ["rate_limited", 429, "too many requests fake-secret"],
    ["model_unavailable", 404, "No endpoints found for fake-secret"],
  ] as const)("maps outbound provider failure to %s", async (status, code, message) => {
    mocks.generateText.mockImplementation(async () => {
      tracker.noteProviderRequest();
      throw apiError(code, message);
    });

    const result = await probeProviderCapability({ provider: GROQ_PROVIDER });

    expect(result).toMatchObject({ status, outbound_count: 1 });
    const serialized = JSON.stringify(result);
    expect(serialized).not.toContain("fake-secret");
    expect(serialized).not.toContain("raw-secret-body");
    expect(serialized).not.toContain("private-chain-of-thought");
  });

  it("classifies an explicit named-tool rejection", async () => {
    mocks.generateText.mockImplementation(async () => {
      tracker.noteProviderRequest();
      throw apiError(400, "tool_choice named function is unsupported");
    });

    await expect(
      probeProviderCapability({ provider: GROQ_PROVIDER }),
    ).resolves.toMatchObject({
      status: "named_tool_unsupported",
      outbound_count: 1,
    });
  });

  it("classifies prose instead of the forced first tool", async () => {
    mocks.generateText.mockImplementation(async () => {
      tracker.noteProviderRequest();
      return { usage: { inputTokens: 2, outputTokens: 2, totalTokens: 4 } };
    });

    await expect(
      probeProviderCapability({ provider: GROQ_PROVIDER }),
    ).resolves.toMatchObject({ status: "named_tool_unsupported" });
  });

  it("classifies wrong placement content as schema_failed", async () => {
    mocks.generateText.mockImplementation(async (raw: unknown) => {
      const options = generationOptions(raw);
      tracker.noteProviderRequest();
      const wrong: Array<{ row: number; col: number; letter: string }> =
        PROVIDER_CAPABILITY_PLACEMENTS.map((item) => ({ ...item }));
      wrong[3] = { row: 7, col: 7, letter: "Z" };
      await options.tools.validateMove.execute({ placements: wrong });
      return {};
    });

    await expect(
      probeProviderCapability({ provider: GROQ_PROVIDER }),
    ).resolves.toMatchObject({ status: "schema_failed" });
  });

  it("classifies an AI SDK invalid tool input error as schema_failed", async () => {
    mocks.generateText.mockImplementation(async () => {
      tracker.noteProviderRequest();
      throw Object.assign(new Error("invalid tool input fake-secret"), {
        name: "AI_InvalidToolInputError",
        toolInput: "fake-secret",
      });
    });

    await expect(
      probeProviderCapability({ provider: GROQ_PROVIDER }),
    ).resolves.toMatchObject({ status: "schema_failed" });
  });

  it("classifies an undeclared wrong tool call as schema_failed", async () => {
    mocks.generateText.mockImplementation(async () => {
      tracker.noteProviderRequest();
      throw Object.assign(new Error("tool does not exist fake-secret"), {
        name: "AI_NoSuchToolError",
        toolName: "wrongTool",
      });
    });

    await expect(
      probeProviderCapability({ provider: GROQ_PROVIDER }),
    ).resolves.toMatchObject({ status: "schema_failed" });
  });

  it("rejects finishMove before validateMove", async () => {
    mocks.generateText.mockImplementation(async (raw: unknown) => {
      const options = generationOptions(raw);
      tracker.noteProviderRequest();
      await options.tools.finishMove.execute({ ready: true });
      return {};
    });

    await expect(
      probeProviderCapability({ provider: GROQ_PROVIDER }),
    ).resolves.toMatchObject({ status: "tool_continuation_failed" });
  });

  it("requires finishMove after a successful validate result", async () => {
    mocks.generateText.mockImplementation(async (raw: unknown) => {
      const options = generationOptions(raw);
      tracker.noteProviderRequest();
      await options.tools.validateMove.execute({
        placements: PROVIDER_CAPABILITY_PLACEMENTS.map((item) => ({ ...item })),
      });
      tracker.noteProviderRequest();
      return { usage: { inputTokens: 2, outputTokens: 2, totalTokens: 4 } };
    });

    await expect(
      probeProviderCapability({ provider: GROQ_PROVIDER }),
    ).resolves.toMatchObject({
      status: "tool_continuation_failed",
      outbound_count: 2,
    });
  });

  it("rejects validate -> validate -> finish instead of accepting a loose loop", async () => {
    let finishReached = false;
    mocks.generateText.mockImplementation(async (raw: unknown) => {
      const options = generationOptions(raw);
      const placements = PROVIDER_CAPABILITY_PLACEMENTS.map((item) => ({
        ...item,
      }));
      tracker.noteProviderRequest();
      await options.tools.validateMove.execute({ placements });
      tracker.noteProviderRequest();
      await options.tools.validateMove.execute({ placements });
      finishReached = true;
      await options.tools.finishMove.execute({ ready: true });
      return {};
    });

    const result = await probeProviderCapability({ provider: GROQ_PROVIDER });

    expect(result.status).toBe("tool_continuation_failed");
    expect(finishReached).toBe(false);
  });

  it("latches a repeated validate failure even when the SDK catches the tool error", async () => {
    mocks.generateText.mockImplementation(async (raw: unknown) => {
      const options = generationOptions(raw);
      const placements = PROVIDER_CAPABILITY_PLACEMENTS.map((item) => ({
        ...item,
      }));
      tracker.noteProviderRequest();
      await options.tools.validateMove.execute({ placements });
      tracker.noteProviderRequest();
      try {
        await options.tools.validateMove.execute({ placements });
      } catch {
        // AI SDK tool execution converts this into a tool-error result.
      }
      tracker.noteProviderRequest();
      await options.tools.finishMove.execute({ ready: true });
      return {};
    });

    await expect(
      probeProviderCapability({ provider: GROQ_PROVIDER }),
    ).resolves.toMatchObject({
      status: "tool_continuation_failed",
      outbound_count: 3,
    });
  });

  it("latches an invalid continuation call reported by the SDK", async () => {
    mocks.generateText.mockImplementation(async (raw: unknown) => {
      const options = generationOptions(raw);
      tracker.noteProviderRequest();
      await options.tools.validateMove.execute({
        placements: PROVIDER_CAPABILITY_PLACEMENTS.map((item) => ({ ...item })),
      });
      tracker.noteProviderRequest();
      options.onStepFinish({
        toolCalls: [
          {
            dynamic: true,
            invalid: true,
            error: Object.assign(new Error("invalid tool input"), {
              name: "AI_InvalidToolInputError",
            }),
          },
        ],
        content: [],
      });
      await options.tools.finishMove.execute({ ready: true });
      return {};
    });

    await expect(
      probeProviderCapability({ provider: GROQ_PROVIDER }),
    ).resolves.toMatchObject({ status: "schema_failed" });
  });

  it("classifies wrong finish ready input as schema_failed", async () => {
    mocks.generateText.mockImplementation(async (raw: unknown) => {
      const options = generationOptions(raw);
      tracker.noteProviderRequest();
      await options.tools.validateMove.execute({
        placements: PROVIDER_CAPABILITY_PLACEMENTS.map((item) => ({ ...item })),
      });
      tracker.noteProviderRequest();
      await options.tools.finishMove.execute({ ready: false });
      return {};
    });

    await expect(
      probeProviderCapability({ provider: GROQ_PROVIDER }),
    ).resolves.toMatchObject({ status: "schema_failed" });
  });

  it("returns a bounded timeout without leaking the pending provider error", async () => {
    mocks.generateText.mockImplementation(
      (raw: unknown) =>
        new Promise((_, reject) => {
          const options = generationOptions(raw);
          tracker.noteProviderRequest();
          options.abortSignal.addEventListener(
            "abort",
            () => reject(apiError(499, "aborted fake-secret")),
            { once: true },
          );
        }),
    );

    const result = await probeProviderCapability({
      provider: GROQ_PROVIDER,
      timeout_ms: 1,
    });

    expect(result).toMatchObject({ status: "timeout", outbound_count: 1 });
    expect(JSON.stringify(result)).not.toContain("fake-secret");
  });

  it("sanitizes unknown failures and exposes every declared status exactly once", async () => {
    mocks.generateText.mockImplementation(async () => {
      tracker.noteProviderRequest();
      throw Object.assign(new Error("novel fake-secret response"), {
        rawBody: "raw-secret-body",
        reasoning: "private-chain-of-thought",
      });
    });

    const result = await probeProviderCapability({ provider: GROQ_PROVIDER });
    expect(result.status).toBe("unknown");
    expect(PROVIDER_CAPABILITY_STATUSES).toEqual([
      "pass",
      "not_configured",
      "auth_failed",
      "rate_limited",
      "model_unavailable",
      "named_tool_unsupported",
      "tool_continuation_failed",
      "schema_failed",
      "timeout",
      "unknown",
    ]);
    const serialized = JSON.stringify(result);
    expect(serialized).not.toContain("fake-secret");
    expect(serialized).not.toContain("raw-secret-body");
    expect(serialized).not.toContain("private-chain-of-thought");
  });
});
