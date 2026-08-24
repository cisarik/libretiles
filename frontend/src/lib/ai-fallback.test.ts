import { describe, expect, it, vi } from "vitest";
import type { AiMoveStreamTerminal } from "./ai-move-stream";
import {
  aiMoveRequestBody,
  buildFallbackQueue,
  canStartAttempt,
  decideNextFallbackAttempt,
  fallbackQueueForCatalogFailure,
  gameStateAllowsRetry,
  orchestrateFallbackTurn,
  providerBadgeLabel,
  remainingTimeoutSeconds,
  type CatalogPair,
  type ReconciliationView,
  type TurnAnchor,
} from "./ai-fallback";

const OPENROUTER_GEMMA = "google/gemma-4-31b-it:free";
const NVIDIA_NIM_NEMOTRON = "nvidia/nemotron-3-super-120b-a12b";
const OPENROUTER_NEMOTRON = "nvidia/nemotron-3-super-120b-a12b:free";
const OPENROUTER_GLM = "z-ai/glm-5.2:free";
const OPENROUTER_GEMMA_SMALL = "google/gemma-4-26b-a4b-it:free";

const FULL_CATALOG: CatalogPair[] = [
  { provider: "openrouter", model_id: OPENROUTER_GEMMA },
  { provider: "nvidia-nim", model_id: NVIDIA_NIM_NEMOTRON },
  { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
  { provider: "openrouter", model_id: OPENROUTER_GLM },
  { provider: "openrouter", model_id: OPENROUTER_GEMMA_SMALL },
];

const ANCHOR: TurnAnchor = {
  gameId: "game-1",
  moveCount: 4,
  aiSlot: 1,
};

function activeState(
  overrides: Partial<ReconciliationView> = {},
): ReconciliationView {
  return {
    game_id: "game-1",
    move_count: 4,
    status: "active",
    current_turn_slot: 1,
    game_over: false,
    ...overrides,
  };
}

const CODED_AUTH: AiMoveStreamTerminal = {
  kind: "coded_provider_error",
  code: "provider_auth_failed",
  message: "missing NIM key",
};

const CODED_429: AiMoveStreamTerminal = {
  kind: "coded_provider_error",
  code: "provider_rate_limited",
  message: "nested OpenRouter 429",
};

const CODED_UNAVAILABLE: AiMoveStreamTerminal = {
  kind: "coded_provider_error",
  code: "provider_unavailable",
  message: "provider down",
};

describe("buildFallbackQueue", () => {
  it("orders selected, unused provider, then next unused catalog pair", () => {
    expect(buildFallbackQueue(OPENROUTER_GEMMA, FULL_CATALOG)).toEqual([
      { provider: "openrouter", model_id: OPENROUTER_GEMMA },
      { provider: "nvidia-nim", model_id: NVIDIA_NIM_NEMOTRON },
      { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
    ]);
  });

  it("starts from the selected NIM pair then the first unused provider", () => {
    expect(buildFallbackQueue(NVIDIA_NIM_NEMOTRON, FULL_CATALOG)).toEqual([
      { provider: "nvidia-nim", model_id: NVIDIA_NIM_NEMOTRON },
      { provider: "openrouter", model_id: OPENROUTER_GEMMA },
      { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
    ]);
  });

  it("de-duplicates exact provider/model pairs and caps at three", () => {
    const duplicated: CatalogPair[] = [
      ...FULL_CATALOG,
      { provider: "openrouter", model_id: OPENROUTER_GEMMA },
    ];
    const queue = buildFallbackQueue(OPENROUTER_GEMMA, duplicated);
    expect(queue).toHaveLength(3);
    const keys = queue.map((pair) => `${pair.provider}:${pair.model_id}`);
    expect(new Set(keys).size).toBe(3);
  });

  it("returns an empty queue for an empty catalog", () => {
    expect(buildFallbackQueue(OPENROUTER_GEMMA, [])).toEqual([]);
  });

  it("queues up to three models from a single-provider catalog", () => {
    const singleProvider: CatalogPair[] = [
      { provider: "openrouter", model_id: OPENROUTER_GEMMA },
      { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
      { provider: "openrouter", model_id: OPENROUTER_GLM },
      { provider: "openrouter", model_id: OPENROUTER_GEMMA_SMALL },
    ];
    expect(buildFallbackQueue(OPENROUTER_GEMMA, singleProvider)).toEqual([
      { provider: "openrouter", model_id: OPENROUTER_GEMMA },
      { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
      { provider: "openrouter", model_id: OPENROUTER_GLM },
    ]);
  });

  it("skips a selected id that is missing from the catalog", () => {
    expect(buildFallbackQueue("missing/model", FULL_CATALOG)).toEqual([
      { provider: "openrouter", model_id: OPENROUTER_GEMMA },
      { provider: "nvidia-nim", model_id: NVIDIA_NIM_NEMOTRON },
      { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
    ]);
  });
});

describe("catalog failure and timeout helpers", () => {
  it("does not invent a static fallback list when the catalog fetch failed", () => {
    expect(fallbackQueueForCatalogFailure(NVIDIA_NIM_NEMOTRON)).toEqual([
      { provider: "nvidia-nim", model_id: NVIDIA_NIM_NEMOTRON },
    ]);
  });

  it("refuses another attempt when remaining timeout is under 15 seconds", () => {
    expect(remainingTimeoutSeconds(0, 30, 16_000)).toBe(14);
    expect(canStartAttempt(14)).toBe(false);
    expect(canStartAttempt(15)).toBe(true);
    expect(
      decideNextFallbackAttempt({
        attemptIndex: 1,
        queueLength: 3,
        previous: CODED_429,
        remainingSeconds: 14,
        reconciliationAllowsRetry: true,
      }),
    ).toEqual({ action: "stop", reason: "deadline" });
  });

  it("labels Settings/Play provider badges", () => {
    expect(providerBadgeLabel("openrouter")).toBe("OpenRouter");
    expect(providerBadgeLabel("nvidia-nim")).toBe("NVIDIA NIM");
  });

  it("keeps the persisted preference in model_id across runtime attempts", () => {
    const first = aiMoveRequestBody({
      gameId: "game-1",
      token: "t",
      preferenceModelId: OPENROUTER_GEMMA,
      runtimeModelId: NVIDIA_NIM_NEMOTRON,
      timeout: 40,
      maxSteps: 30,
    });
    const second = aiMoveRequestBody({
      gameId: "game-1",
      token: "t",
      preferenceModelId: OPENROUTER_GEMMA,
      runtimeModelId: OPENROUTER_NEMOTRON,
      timeout: 22,
      maxSteps: 30,
    });
    expect(first.model_id).toBe(OPENROUTER_GEMMA);
    expect(second.model_id).toBe(OPENROUTER_GEMMA);
    expect(first.runtime_model_id).toBe(NVIDIA_NIM_NEMOTRON);
    expect(second.runtime_model_id).toBe(OPENROUTER_NEMOTRON);
  });
});

describe("gameStateAllowsRetry", () => {
  it("allows retry only when the same active AI turn is still pending", () => {
    expect(gameStateAllowsRetry(ANCHOR, activeState())).toBe(true);
  });

  it("blocks retry when move_count changed", () => {
    expect(
      gameStateAllowsRetry(ANCHOR, activeState({ move_count: 5 })),
    ).toBe(false);
  });

  it("blocks retry when the turn owner changed", () => {
    expect(
      gameStateAllowsRetry(ANCHOR, activeState({ current_turn_slot: 0 })),
    ).toBe(false);
  });

  it("blocks retry when the game is over", () => {
    expect(
      gameStateAllowsRetry(
        ANCHOR,
        activeState({ game_over: true, status: "finished" }),
      ),
    ).toBe(false);
  });

  it("blocks retry when reconciliation is missing", () => {
    expect(gameStateAllowsRetry(ANCHOR, null)).toBe(false);
  });
});

describe("orchestrateFallbackTurn", () => {
  const baseOpts = {
    queue: buildFallbackQueue(OPENROUTER_GEMMA, FULL_CATALOG),
    turnStartedAtMs: 0,
    aiTimeoutSeconds: 60,
    now: () => 1_000,
    anchor: ANCHOR,
  };

  it("does not start a second stream when Django state cannot be reconciled", async () => {
    const runStream = vi.fn(async () => CODED_429);
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () => null,
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(1);
    expect(result.stopReason).toBe("reconciliation");
  });

  it("does not start a second stream after a persisted move_count change", async () => {
    const fetchGameState = vi.fn(async () => activeState({ move_count: 5 }));
    const runStream = vi.fn(async () => CODED_429);
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState,
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(1);
    expect(fetchGameState).toHaveBeenCalledTimes(1);
    expect(result.posts).toHaveLength(1);
    expect(result.stopReason).toBe("reconciliation");
  });

  it("does not start a second stream after the turn leaves the AI", async () => {
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () => activeState({ current_turn_slot: 0 }),
      runStream: async () => CODED_AUTH,
    });
    expect(result.posts).toHaveLength(1);
    expect(result.stopReason).toBe("reconciliation");
  });

  it("does not start a second stream after game-over", async () => {
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () =>
        activeState({ game_over: true, status: "finished" }),
      runStream: async () => CODED_UNAVAILABLE,
    });
    expect(result.posts).toHaveLength(1);
    expect(result.stopReason).toBe("reconciliation");
  });

  it("retries a missing NIM key onto the next queued model", async () => {
    const terminals: AiMoveStreamTerminal[] = [
      CODED_AUTH,
      { kind: "done", data: { type: "done", ok: true, action: "pass" } },
    ];
    const runStream = vi.fn(async () => terminals.shift()!);
    const result = await orchestrateFallbackTurn({
      queue: buildFallbackQueue(NVIDIA_NIM_NEMOTRON, FULL_CATALOG),
      turnStartedAtMs: 0,
      aiTimeoutSeconds: 60,
      now: () => 1_000,
      anchor: ANCHOR,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(2);
    expect(result.posts[0]?.pair.model_id).toBe(NVIDIA_NIM_NEMOTRON);
    expect(result.posts[1]?.pair.provider).toBe("openrouter");
    expect(result.stopReason).toBe("done");
  });

  it("retries a nested OpenRouter 429 onto NIM as the second model", async () => {
    const terminals: AiMoveStreamTerminal[] = [
      CODED_429,
      { kind: "done", data: { type: "done", ok: true, action: "place" } },
    ];
    const runStream = vi.fn(async () => terminals.shift()!);
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(result.posts).toHaveLength(2);
    expect(result.posts[1]?.pair).toEqual({
      provider: "nvidia-nim",
      model_id: NVIDIA_NIM_NEMOTRON,
    });
    expect(result.stopReason).toBe("done");
  });

  it("stops after a successful second-model done and does not open a third stream", async () => {
    const terminals: AiMoveStreamTerminal[] = [
      CODED_429,
      { kind: "done", data: { type: "done", ok: true, action: "exchange" } },
    ];
    const runStream = vi.fn(async () => terminals.shift()!);
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(2);
    expect(result.stopReason).toBe("done");
  });

  it("exhausts the queue when every provider is unavailable", async () => {
    const runStream = vi.fn(async () => CODED_UNAVAILABLE);
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(3);
    expect(result.stopReason).toBe("queue_exhausted");
    expect(result.lastTerminal?.kind).toBe("coded_provider_error");
  });

  it("attempts only the selected model when the catalog fetch failed", async () => {
    const runStream = vi.fn(async () => CODED_429);
    const result = await orchestrateFallbackTurn({
      queue: fallbackQueueForCatalogFailure(OPENROUTER_GEMMA),
      turnStartedAtMs: 0,
      aiTimeoutSeconds: 60,
      now: () => 1_000,
      anchor: ANCHOR,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(1);
    expect(result.posts[0]?.pair.model_id).toBe(OPENROUTER_GEMMA);
    expect(result.stopReason).toBe("queue_exhausted");
  });

  it("does not start a second stream when the overall deadline is exhausted", async () => {
    let nowMs = 1_000;
    const fetchGameState = vi.fn(async () => activeState());
    const runStream = vi.fn(async () => {
      nowMs = 50_000;
      return CODED_429;
    });
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      now: () => nowMs,
      aiTimeoutSeconds: 60,
      fetchGameState,
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(1);
    expect(fetchGameState).not.toHaveBeenCalled();
    expect(result.stopReason).toBe("deadline");
  });

  it("does not fallback after a generic backend error", async () => {
    const runStream = vi.fn(async (): Promise<AiMoveStreamTerminal> => ({
      kind: "generic_error",
      message: "authentication token expired",
    }));
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(1);
    expect(result.stopReason).toBe("generic_error");
  });
});
