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
