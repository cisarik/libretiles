import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  COMPLETION_SOURCES,
  SHIPPED_PROVIDER_ORIGINS,
  buildDiagnosticQueue,
  derivedExternalProviderInvocations,
  installFetchGuard,
  liveOptInEnabled,
  originOf,
  runDiagnosticTurn,
  serializeTerminalObservation,
} from "./ai-play-diagnostic";
import type { AiMoveStreamTerminal } from "./ai-move-stream";

const fallbackHarness = vi.hoisted(() => ({
  captured: [] as Array<Record<string, unknown>>,
  runStreamHook: null as
    | null
    | ((opts: Record<string, unknown>) => Promise<unknown>),
}));

vi.mock("./ai-fallback", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./ai-fallback")>();
  return {
    ...actual,
    orchestrateFallbackTurn: async (opts: Record<string, unknown>) => {
      fallbackHarness.captured.push(opts);
      if (fallbackHarness.runStreamHook !== null) {
        const streamResult = await fallbackHarness.runStreamHook(opts);
        return {
          posts: [],
          providerRequestsUsed: 0,
          lastTerminal: streamResult,
        };
      }
      return {
        posts: [],
        providerRequestsUsed: 0,
        lastTerminal: { kind: "generic_error", message: "diagnostic capture" },
      };
    },
  };
});

const NIM = {
  provider: "nvidia-nim",
  model_id: "nvidia/nemotron-3-super-120b-a12b",
};
const GEMMA = {
  provider: "openrouter",
  model_id: "google/gemma-4-31b-it:free",
};
const GLM = {
  provider: "openrouter",
  model_id: "z-ai/glm-5.2:free",
};
const CATALOG = [
  GEMMA,
  NIM,
  { provider: "openrouter", model_id: "nvidia/nemotron-3-super-120b-a12b:free" },
  GLM,
  { provider: "openrouter", model_id: "google/gemma-4-26b-a4b-it:free" },
];

describe("ai-play-diagnostic helpers", () => {
  it("keeps selected-only queues at the exact requested pair", () => {
    const queue = buildDiagnosticQueue({
      provider: NIM.provider,
      modelId: NIM.model_id,
      queueMode: "selected-only",
      catalog: CATALOG,
    });
    expect(queue).toEqual([NIM]);
  });

  it("builds a preference-first catalog-fallback queue of at most three pairs", () => {
    const queue = buildDiagnosticQueue({
      provider: NIM.provider,
      modelId: NIM.model_id,
      queueMode: "catalog-fallback",
      catalog: CATALOG,
    });
    expect(queue[0]).toEqual(NIM);
    expect(queue.length).toBeLessThanOrEqual(3);
    expect(queue.length).toBeGreaterThanOrEqual(1);
    const keys = queue.map((row) => `${row.provider}\0${row.model_id}`);
    expect(new Set(keys).size).toBe(queue.length);
  });

  it("serializes the six completion sources and drops headers and bodies", () => {
    for (const source of COMPLETION_SOURCES) {
      const terminal: AiMoveStreamTerminal = {
        kind: "done",
        data: {
          type: "done",
          action: "place",
          completion_source: source,
          words: [{ word: "SČÍTALO", score: 82 }],
          points: 82,
          Authorization: "Bearer secret-token",
          token: "should-drop",
          prompt: "SEARCH PROFILE",
        },
      };
      const observation = serializeTerminalObservation({
        terminal,
        attempts: [
          {
            provider: NIM.provider,
            model_id: NIM.model_id,
            timeout_seconds: 60,
            step_grant: 30,
            provider_requests_used: 0,
          },
        ],
        queue: [NIM],
        turnProviderRequestsUsed: 0,
        lostTerminal: false,
        externalProviderInvocations: 0,
        backendOrigins: ["http://127.0.0.1:9"],
        foreignOrigins: [],
      });
      expect(observation.completion_source).toBe(source);
      expect(JSON.stringify(observation)).not.toContain("Bearer");
      expect(JSON.stringify(observation)).not.toContain("secret-token");
      expect(JSON.stringify(observation)).not.toContain("SEARCH PROFILE");
      expect(observation.formed_words).toEqual(["SČÍTALO"]);
    }
  });

  it("treats live mode as refused without the sentinel", () => {
    expect(liveOptInEnabled({} as NodeJS.ProcessEnv)).toBe(false);
    expect(
      liveOptInEnabled({
        NODE_ENV: "test",
        LIBRETILES_AI_PLAY_LIVE: "1",
      }),
    ).toBe(true);
  });
});

const LIVE_WORKER_SOURCE = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "ai-play-diagnostic.live.worker.test.ts"),
  "utf8",
);
const BACKEND = "http://127.0.0.1:9";

describe("ai-play-diagnostic fetch guard and live driver contract", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("test_fetch_guard_counts_provider_origin_requests", async () => {
    const original = vi.fn(async () => new Response("ok"));
    globalThis.fetch = original as unknown as typeof fetch;
    const guard = installFetchGuard(BACKEND, { mode: "live" });
    try {
      await fetch("https://openrouter.ai/api/v1/chat/completions");
      await fetch("https://integrate.api.nvidia.com/v1/chat/completions");
      await fetch(`${BACKEND}/api/catalog/models/`);
      expect(guard.provider).toEqual([
        "https://openrouter.ai",
        "https://integrate.api.nvidia.com",
      ]);
      expect(derivedExternalProviderInvocations(guard.provider)).toBe(2);
      expect(guard.backend).toEqual([BACKEND]);
    } finally {
      guard.restore();
    }
  });

  it("test_fetch_guard_blocks_provider_origins_in_fake_mode", async () => {
    const original = vi.fn(async () => new Response("ok"));
    globalThis.fetch = original as unknown as typeof fetch;
    const guard = installFetchGuard(BACKEND, { mode: "fake" });
    try {
      await expect(fetch("https://openrouter.ai/api/v1/chat/completions")).rejects.toThrow(
        /fake mode blocked foreign origin/,
      );
      await expect(
        fetch("https://integrate.api.nvidia.com/v1/chat/completions"),
      ).rejects.toThrow(/fake mode blocked foreign origin/);
      expect(guard.provider).toEqual([]);
      expect(derivedExternalProviderInvocations(guard.provider)).toBe(0);
      expect(guard.foreign).toEqual([
        "https://openrouter.ai",
        "https://integrate.api.nvidia.com",
      ]);
      expect(original).not.toHaveBeenCalled();
    } finally {
      guard.restore();
    }
  });

  it("test_fetch_guard_allows_only_the_two_shipped_provider_bases_in_live_mode", async () => {
    expect(SHIPPED_PROVIDER_ORIGINS).toEqual([
      "https://openrouter.ai",
      "https://integrate.api.nvidia.com",
    ]);
    const original = vi.fn(async () => new Response("ok"));
    globalThis.fetch = original as unknown as typeof fetch;
    const guard = installFetchGuard(BACKEND, { mode: "live" });
    try {
      await fetch("https://openrouter.ai/api/v1");
      await fetch("https://integrate.api.nvidia.com/v1");
      await expect(fetch("https://api.groq.com/openai/v1")).rejects.toThrow(
        /live mode blocked origin/,
      );
      await expect(fetch("https://example.com/")).rejects.toThrow(/live mode blocked origin/);
      expect(guard.provider).toEqual([
        "https://openrouter.ai",
        "https://integrate.api.nvidia.com",
      ]);
      expect(guard.foreign).toEqual(["https://api.groq.com", "https://example.com"]);
      expect(originOf("https://openrouter.ai/api/v1/models")).toBe("https://openrouter.ai");
    } finally {
      guard.restore();
    }
  });

  it("test_external_provider_invocations_is_derived_not_constant", async () => {
    const unusedPost = async () => {
      throw new Error("post must not run");
    };
    const zero = await runDiagnosticTurn({
      post: unusedPost,
      backendUrl: BACKEND,
      gameId: "00000000-0000-0000-0000-000000000001",
      token: "diagnostic-test-token",
      provider: NIM.provider,
      modelId: NIM.model_id,
      timeoutSeconds: 5,
      maxSteps: 5,
      queueMode: "selected-only",
      script: "generic_unchanged",
      providerOrigins: [],
    });
    expect(zero.external_provider_invocations).toBe(0);
    const original = vi.fn(async () => new Response("ok"));
    globalThis.fetch = original as unknown as typeof fetch;
    const guard = installFetchGuard(BACKEND, { mode: "live" });
    try {
      await fetch("https://openrouter.ai/api/v1/chat/completions");
      const incremented = await runDiagnosticTurn({
        post: unusedPost,
        backendUrl: BACKEND,
        gameId: "00000000-0000-0000-0000-000000000001",
        token: "diagnostic-test-token",
        provider: NIM.provider,
        modelId: NIM.model_id,
        timeoutSeconds: 5,
        maxSteps: 5,
        queueMode: "selected-only",
        script: "generic_unchanged",
        providerOrigins: guard.provider,
      });
      expect(incremented.external_provider_invocations).toBe(1);
      expect(incremented.external_provider_invocations).not.toBe(
        zero.external_provider_invocations,
      );
    } finally {
      guard.restore();
    }
  });

  it("test_live_driver_does_not_mock_the_runtime_registry", () => {
    expect(LIVE_WORKER_SOURCE).not.toMatch(/vi\.mock\(\s*["'`]ai["'`]/);
    expect(LIVE_WORKER_SOURCE).not.toMatch(/vi\.mock\(\s*["'`]@\/lib\/ai-runtimes["'`]/);
    expect(LIVE_WORKER_SOURCE).not.toContain('vi.mock("ai"');
    expect(LIVE_WORKER_SOURCE).not.toContain("vi.mock('ai'");
    expect(LIVE_WORKER_SOURCE).not.toContain('vi.mock("@/lib/ai-runtimes"');
    expect(LIVE_WORKER_SOURCE).not.toContain("vi.mock('@/lib/ai-runtimes'");
  });
});

describe("aiSlot parameterization and credential no-echo", () => {
  const unusedPost = async () => {
    throw new Error("post must not run");
  };
  let originalFetch: typeof fetch | undefined;

  afterEach(() => {
    fallbackHarness.captured = [];
    if (originalFetch) globalThis.fetch = originalFetch;
  });

  function stubBackendFetch(): void {
    originalFetch ??= globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;
      if (url.includes("/api/catalog/models/")) {
        return new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("{}", { status: 404 });
    }) as unknown as typeof fetch;
  }

  async function drive(aiSlot?: number): Promise<unknown> {
    stubBackendFetch();
    return runDiagnosticTurn({
      post: unusedPost,
      backendUrl: BACKEND,
      gameId: "00000000-0000-0000-0000-000000000001",
      token: "jwt-echo-probe-0123456789abcdef",
      provider: NIM.provider,
      modelId: NIM.model_id,
      timeoutSeconds: 5,
      maxSteps: 5,
      queueMode: "selected-only",
      script: "noop_rescue",
      ...(aiSlot === undefined ? {} : { aiSlot }),
    });
  }

  it("keeps the product anchor at seat 1 when aiSlot is omitted", async () => {
    await drive();
    expect(fallbackHarness.captured).toHaveLength(1);
    const anchor = fallbackHarness.captured[0].anchor as { aiSlot: number };
    expect(anchor.aiSlot).toBe(1);
  });

  it("forwards aiSlot 0 to the fallback anchor for diagnostic seat 0", async () => {
    await drive(0);
    expect(fallbackHarness.captured).toHaveLength(1);
    const anchor = fallbackHarness.captured[0].anchor as { aiSlot: number };
    expect(anchor.aiSlot).toBe(0);
  });

  it("never echoes the minted token into the terminal observation", async () => {
    const observation = (await drive(1)) as { terminal_kind: string };
    expect(observation.terminal_kind).toBe("generic_error");
    expect(JSON.stringify(observation)).not.toContain("jwt-echo-probe-0123456789abcdef");
  });
});

describe("S7 diagnostic target assertion", () => {
  afterEach(() => {
    fallbackHarness.captured = [];
    fallbackHarness.runStreamHook = null;
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  function stubBackendFetch(): void {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;
      if (url.includes("/api/catalog/models/")) {
        return new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("{}", { status: 404 });
    }) as unknown as typeof fetch;
  }

  async function driveWithCapturedPost(targetId: string | undefined): Promise<{
    bodies: Array<Record<string, unknown>>;
    observation: { provider_identity?: string } & Record<string, unknown>;
  }> {
    const bodies: Array<Record<string, unknown>> = [];
    fallbackHarness.runStreamHook = async (opts) => {
      const streamOpts = opts as {
        runStream: (request: {
          pair: { provider: string; model_id: string };
          timeoutSeconds: number;
          maxStepsRemaining: number;
        }) => Promise<unknown>;
      };
      return streamOpts.runStream({
        pair: { provider: "diagnostic-target", model_id: "vendor/target-model" },
        timeoutSeconds: 30,
        maxStepsRemaining: 10,
      });
    };
    const observation = await runDiagnosticTurn({
      post: async (request) => {
        bodies.push(JSON.parse(await request.text()) as Record<string, unknown>);
        return new Response("{}", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      },
      backendUrl: BACKEND,
      gameId: "00000000-0000-0000-0000-000000000001",
      token: "diagnostic-test-token",
      provider: "diagnostic-target",
      modelId: "vendor/target-model",
      timeoutSeconds: 5,
      maxSteps: 5,
      queueMode: "selected-only",
      script: "noop_rescue",
      ...(targetId === undefined ? {} : { diagnosticTargetId: targetId }),
    });
    return { bodies, observation: observation as { provider_identity?: string } & Record<string, unknown> };
  }

  it("puts the diagnostic_target_id selection assertion on the POST body", async () => {
    stubBackendFetch();
    const { bodies, observation } = await driveWithCapturedPost(
      "00000000-0000-0000-0000-0000000000aa",
    );
    expect(bodies).toHaveLength(1);
    expect(bodies[0].diagnostic_target_id).toBe("00000000-0000-0000-0000-0000000000aa");
    expect(observation.provider_identity).toBe(
      "diagnostic-target/00000000-0000-0000-0000-0000000000aa",
    );
    expect(JSON.stringify(observation)).not.toContain("https://");
    expect(JSON.stringify(observation)).not.toContain("credential_env_name");
  });

  it("omits the assertion and provider identity for catalog seats", async () => {
    stubBackendFetch();
    const { bodies, observation } = await driveWithCapturedPost(undefined);
    expect(bodies).toHaveLength(1);
    expect(bodies[0].diagnostic_target_id).toBeUndefined();
    expect(observation.provider_identity).toBeUndefined();
  });
});

describe("S7 installFetchGuard egress policy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("denies provider origins in live mode when the caller passes a deny policy", async () => {
    const original = vi.fn(async () => new Response("ok"));
    globalThis.fetch = original as unknown as typeof fetch;
    const guard = installFetchGuard(BACKEND, { mode: "live", egressMode: "deny" });
    try {
      await expect(fetch("https://openrouter.ai/api/v1/chat/completions")).rejects.toThrow(
        /egress policy/i,
      );
      expect(guard.provider).toEqual([]);
      expect(original).not.toHaveBeenCalled();
    } finally {
      guard.restore();
    }
  });

  it("still denies everything foreign in fake mode before any socket", async () => {
    const original = vi.fn(async () => new Response("ok"));
    globalThis.fetch = original as unknown as typeof fetch;
    const guard = installFetchGuard(BACKEND, { mode: "fake", egressMode: "deny" });
    try {
      await expect(fetch("https://rival.example.com/api/v1/chat/completions")).rejects.toThrow(
        /fake mode blocked foreign origin/,
      );
      expect(guard.foreign).toEqual(["https://rival.example.com"]);
      expect(original).not.toHaveBeenCalled();
    } finally {
      guard.restore();
    }
  });
});
