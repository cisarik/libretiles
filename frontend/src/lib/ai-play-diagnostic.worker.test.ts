import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import {
  installFetchGuard,
  liveOptInEnabled,
  runDiagnosticTurn,
  type FakeScript,
} from "./ai-play-diagnostic";

const harness = vi.hoisted(() => ({
  generateText: vi.fn(async () => ({ text: "{}", steps: [] })),
  getLanguageRuntime: vi.fn(async () => ({
    model: { provider: "diagnostic", modelId: "fake" },
    tracker: {
      noteProviderRequest: vi.fn(),
      recordUsage: vi.fn(),
      recordRetryAfter: vi.fn(),
      snapshot: () => ({ provider_requests: 0 }),
    },
  })),
}));

vi.mock("ai", () => ({
  generateText: harness.generateText,
  stepCountIs: (n: number) => n,
  tool: (definition: unknown) => definition,
}));

vi.mock("@/lib/ai-runtimes", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ai-runtimes")>();
  return {
    ...actual,
    getLanguageRuntime: harness.getLanguageRuntime,
  };
});

const isWorker = process.env.LIBRETILES_AI_PLAY_WORKER === "1";

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`missing ${name}`);
  return value;
}

describe("ai-play-diagnostic worker", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.skipIf(isWorker)(
    "sets BACKEND_URL before dynamically importing the route",
    { timeout: 60_000 },
    async () => {
    const origin = "http://127.0.0.1:59999";
    process.env.BACKEND_URL = origin;
    const seen: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        seen.push(url);
        return new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    const { POST } = await import("@/app/api/ai/move/route");
    const response = await POST(
      new NextRequest("http://localhost/api/ai/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          game_id: "00000000-0000-0000-0000-000000000001",
          token: "diagnostic-test-token",
          model_id: "nvidia/nemotron-3-super-120b-a12b",
          timeout: 5,
          max_steps: 5,
        }),
      }),
    );
    await response.text();
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.every((url) => url.startsWith(origin))).toBe(true);
    expect(seen.some((url) => url.includes("localhost:8000"))).toBe(false);
    },
  );

  it.skipIf(!isWorker)(
    "drives one real turn against the ephemeral backend",
    { timeout: 180_000 },
    async () => {
    expect(liveOptInEnabled()).toBe(false);
    const backendUrl = requiredEnv("BACKEND_URL").replace(/\/$/, "");
    process.env.BACKEND_URL = backendUrl;
    const guard = installFetchGuard(new URL(backendUrl).origin, { mode: "fake" });
    try {
      const { POST } = await import("@/app/api/ai/move/route");
      const script = (process.env.LIBRETILES_AI_PLAY_SCRIPT ?? "noop_rescue") as FakeScript;
      const observation = await runDiagnosticTurn({
        post: (request) => POST(request),
        backendUrl,
        gameId: requiredEnv("LIBRETILES_AI_PLAY_GAME_ID"),
        token: requiredEnv("LIBRETILES_AI_PLAY_JWT"),
        provider: requiredEnv("LIBRETILES_AI_PLAY_PROVIDER"),
        modelId: requiredEnv("LIBRETILES_AI_PLAY_MODEL_ID"),
        timeoutSeconds: Number(process.env.LIBRETILES_AI_PLAY_TIMEOUT ?? "60"),
        maxSteps: Number(process.env.LIBRETILES_AI_PLAY_MAX_STEPS ?? "30"),
        queueMode:
          process.env.LIBRETILES_AI_PLAY_QUEUE_MODE === "catalog-fallback"
            ? "catalog-fallback"
            : "selected-only",
        script,
        backendOrigins: guard.backend,
        foreignOrigins: guard.foreign,
        providerOrigins: guard.provider,
        executedRuntimeMode: "fake",
        driver: "fake",
      });
      observation.backend_origins = [...new Set(guard.backend)];
      observation.foreign_origins = [...new Set(guard.foreign)];
      observation.external_provider_invocations = guard.provider.length;
      observation.executed_runtime_mode = "fake";
      observation.driver = "fake";
      observation.sentinel_present = liveOptInEnabled();
      expect(observation.foreign_origins).toEqual([]);
      if (script !== "generic_unchanged") {
        expect(observation.backend_origins.length).toBeGreaterThan(0);
        expect(
          observation.backend_origins.every((origin) => origin === new URL(backendUrl).origin),
        ).toBe(true);
      }
      const output = requiredEnv("LIBRETILES_AI_PLAY_OBSERVATION");
      const { writeFileSync } = await import("node:fs");
      writeFileSync(output, `${JSON.stringify(observation)}\n`, "utf8");
    } finally {
      guard.restore();
    }
    },
  );
});
