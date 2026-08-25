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
  providerRequestsUsedFromTerminal,
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

/** Newest-first catalog order as returned by /api/catalog/models/. */
const NEWEST_FIRST_CATALOG: CatalogPair[] = [
  { provider: "openrouter", model_id: OPENROUTER_GLM },
  { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
  { provider: "openrouter", model_id: OPENROUTER_GEMMA_SMALL },
  { provider: "nvidia-nim", model_id: NVIDIA_NIM_NEMOTRON },
  { provider: "openrouter", model_id: OPENROUTER_GEMMA },
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

function doneWith(used?: number): AiMoveStreamTerminal {
  return {
    kind: "done",
    data:
      used === undefined
        ? { type: "done", ok: true, action: "place" }
        : { type: "done", ok: true, action: "place", provider_requests_used: used },
  };
}

describe("buildFallbackQueue", () => {
  it("puts a valid preference first then follows untouched catalog order", () => {
    expect(buildFallbackQueue(OPENROUTER_NEMOTRON, NEWEST_FIRST_CATALOG)).toEqual([
      { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
      { provider: "openrouter", model_id: OPENROUTER_GLM },
      { provider: "openrouter", model_id: OPENROUTER_GEMMA_SMALL },
    ]);
  });

  it("starts at catalog row 1 when the preference is stale or missing", () => {
    expect(buildFallbackQueue("gone/model:free", NEWEST_FIRST_CATALOG)).toEqual([
      { provider: "openrouter", model_id: OPENROUTER_GLM },
      { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
      { provider: "openrouter", model_id: OPENROUTER_GEMMA_SMALL },
    ]);
    expect(buildFallbackQueue(null, NEWEST_FIRST_CATALOG)).toEqual([
      { provider: "openrouter", model_id: OPENROUTER_GLM },
      { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
      { provider: "openrouter", model_id: OPENROUTER_GEMMA_SMALL },
    ]);
    expect(buildFallbackQueue(NVIDIA_NIM_NEMOTRON, NEWEST_FIRST_CATALOG)).toEqual([
      { provider: "nvidia-nim", model_id: NVIDIA_NIM_NEMOTRON },
      { provider: "openrouter", model_id: OPENROUTER_GLM },
      { provider: "openrouter", model_id: OPENROUTER_NEMOTRON },
    ]);
  });

  it("gives Play and Judge identical queues for identical inputs", () => {
    const playQueue = buildFallbackQueue(OPENROUTER_GEMMA, NEWEST_FIRST_CATALOG);
    const judgeQueue = buildFallbackQueue(OPENROUTER_GEMMA, NEWEST_FIRST_CATALOG);
    expect(playQueue).toEqual(judgeQueue);
    expect(playQueue).toHaveLength(3);
  });

  it("de-duplicates exact pairs and never exceeds three attempts", () => {
    const duplicated: CatalogPair[] = [
      ...NEWEST_FIRST_CATALOG,
      { provider: "openrouter", model_id: OPENROUTER_GLM },
    ];
    const queue = buildFallbackQueue(OPENROUTER_GLM, duplicated);
    expect(queue).toHaveLength(3);
    const keys = queue.map((pair) => `${pair.provider}:${pair.model_id}`);
    expect(new Set(keys).size).toBe(3);
  });

  it("returns an empty queue for an empty catalog", () => {
    expect(buildFallbackQueue(OPENROUTER_GEMMA, [])).toEqual([]);
  });

  it("drops structurally invalid rows such as paid or unknown-provider ids", () => {
    const dirty: CatalogPair[] = [
      { provider: "openrouter", model_id: "openai/gpt-5-mini" },
      { provider: "anthropic", model_id: "anthropic/claude:free" },
      { provider: "nvidia-nim", model_id: OPENROUTER_GEMMA },
      { provider: "openrouter", model_id: OPENROUTER_GLM },
    ];
    expect(buildFallbackQueue("", dirty)).toEqual([
      { provider: "openrouter", model_id: OPENROUTER_GLM },
    ]);
  });
});

describe("catalog failure and timeout helpers", () => {
  it("keeps only a playable selected id when the catalog fetch failed", () => {
    expect(fallbackQueueForCatalogFailure(OPENROUTER_GEMMA)).toEqual([
      { provider: "openrouter", model_id: OPENROUTER_GEMMA },
    ]);
    expect(fallbackQueueForCatalogFailure(NVIDIA_NIM_NEMOTRON)).toEqual([
      { provider: "nvidia-nim", model_id: NVIDIA_NIM_NEMOTRON },
    ]);
  });

  it("fails closed with an empty queue for an unplayable selected id", () => {
    expect(fallbackQueueForCatalogFailure("openai/gpt-5-mini")).toEqual([]);
    expect(fallbackQueueForCatalogFailure("")).toEqual([]);
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

describe("providerRequestsUsedFromTerminal", () => {
  it("reads usage from done data and error terminals only", () => {
    expect(providerRequestsUsedFromTerminal(doneWith(7))).toBe(7);
    expect(providerRequestsUsedFromTerminal(CODED_429)).toBe(0);
    expect(
      providerRequestsUsedFromTerminal({
        kind: "coded_provider_error",
        code: "provider_rate_limited",
        message: "429",
        providerRequestsUsed: 3,
      }),
    ).toBe(3);
    expect(
      providerRequestsUsedFromTerminal({
        kind: "generic_error",
        message: "boom",
        providerRequestsUsed: 2,
      }),
    ).toBe(2);
    expect(
      providerRequestsUsedFromTerminal({ kind: "no_terminal" }),
    ).toBe(0);
    expect(providerRequestsUsedFromTerminal(doneWith(-4))).toBe(0);
  });
});

describe("orchestrateFallbackTurn", () => {
  const baseOpts = {
    queue: buildFallbackQueue("", NEWEST_FIRST_CATALOG),
    turnStartedAtMs: 0,
    aiTimeoutSeconds: 60,
    maxStepsTotal: 30,
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

  it("retries onto the next queued model after a reported failure", async () => {
    const terminals: AiMoveStreamTerminal[] = [
      CODED_AUTH,
      doneWith(),
    ];
    const runStream = vi.fn(
      async (request: { attemptIndex: number }): Promise<AiMoveStreamTerminal> =>
        request.attemptIndex === 0 ? terminals[0] : terminals[1],
    );
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      queue: buildFallbackQueue(NVIDIA_NIM_NEMOTRON, NEWEST_FIRST_CATALOG),
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(2);
    expect(result.posts[0]?.pair.model_id).toBe(NVIDIA_NIM_NEMOTRON);
    expect(result.posts[0]?.maxStepsRemaining).toBe(30);
    expect(result.stopReason).toBe("done");
  });

  it("shares one whole-turn budget across fallback attempts", async () => {
    let calls = 0;
    const grantedSteps: number[] = [];
    const runStream = vi.fn(async (request: { maxStepsRemaining: number }) => {
      calls += 1;
      grantedSteps.push(request.maxStepsRemaining);
      return {
        kind: "coded_provider_error" as const,
        code: "provider_rate_limited" as const,
        message: "429",
        providerRequestsUsed: 10,
      };
    });
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      maxStepsTotal: 20,
      fetchGameState: async () => activeState(),
      runStream,
    });
    // Attempt 1 grants the full budget minus nothing; attempt 2 gets only
    // what attempt 1 did not use; attempt 3 would fall under the floor.
    expect(calls).toBe(2);
    expect(grantedSteps).toEqual([20, 10]);
    expect(result.stopReason).toBe("budget_exhausted");
    expect(result.providerRequestsUsed).toBe(20);
  });

  it("stops after a successful second-model done and does not open a third stream", async () => {
    const runStream = vi.fn(
      async (request: {
        attemptIndex: number;
      }): Promise<AiMoveStreamTerminal> =>
        request.attemptIndex === 0 ? CODED_429 : doneWith(4),
    );
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(2);
    expect(result.stopReason).toBe("done");
    expect(result.lastTerminal?.kind).toBe("done");
  });

  it("exhausts the queue when every provider is unavailable but reports usage", async () => {
    const runStream = vi.fn(async () => ({
      ...CODED_UNAVAILABLE,
      providerRequestsUsed: 2,
    }));
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      maxStepsTotal: 30,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(3);
    // Reported usage is 2 per failure but each failed attempt conservatively
    // charges the minimum viable attempt floor of 5 steps.
    expect(result.posts.map((post) => post.maxStepsRemaining)).toEqual([
      30, 25, 20,
    ]);
    expect(result.stopReason).toBe("queue_exhausted");
    expect(result.providerRequestsUsed).toBe(6);
  });

  it("attempts only the selected model when the catalog fetch failed", async () => {
    const runStream = vi.fn(async () => CODED_429);
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      queue: fallbackQueueForCatalogFailure(OPENROUTER_GEMMA),
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

  it("returns empty_queue without posting for an empty queue", async () => {
    const runStream = vi.fn();
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      queue: [],
      fetchGameState: async () => activeState(),
      runStream: runStream as never,
    });
    expect(runStream).not.toHaveBeenCalled();
    expect(result.stopReason).toBe("empty_queue");
  });
});
