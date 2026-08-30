import { describe, expect, it, vi } from "vitest";
import type { AiMoveStreamTerminal } from "./ai-move-stream";
import {
  aiMoveRequestBody,
  attemptStepGrant,
  attemptTimeoutSeconds,
  buildFallbackQueue,
  canStartAttempt,
  decideNextFallbackAttempt,
  fallbackQueueForCatalogFailure,
  gameStateAllowsRetry,
  MAX_FALLBACK_ATTEMPTS,
  orchestrateFallbackTurn,
  providerBadgeLabel,
  providerRequestsUsedFromTerminal,
  remainingTimeoutSeconds,
  retryAfterSecondsFromTerminal,
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
    expect(MAX_FALLBACK_ATTEMPTS).toBe(3);
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

  it("allocates exact whole-turn timeout slices including a short tail", () => {
    expect(remainingTimeoutSeconds(0, 30, 16_000)).toBe(14);
    expect(canStartAttempt(14)).toBe(true);
    expect(canStartAttempt(15)).toBe(true);
    expect(attemptTimeoutSeconds(120, 3)).toBe(40);
    expect(attemptTimeoutSeconds(119, 4)).toBe(29);
    expect(attemptTimeoutSeconds(73, 4)).toBe(18);
    expect(attemptTimeoutSeconds(14, 1)).toBe(14);
    expect(attemptTimeoutSeconds(9, 2)).toBe(9);
    expect(attemptTimeoutSeconds(0, 1)).toBe(0);
    expect(
      decideNextFallbackAttempt({
        attemptIndex: 1,
        queueLength: 3,
        previous: CODED_429,
        remainingSeconds: 14,
        reconciliationAllowsRetry: true,
      }),
    ).toEqual({ action: "post", timeoutSeconds: 14 });
  });

  it("reserves exact five-step grants for later lanes", () => {
    expect(attemptStepGrant(30, 3)).toBe(20);
    expect(attemptStepGrant(50, 5)).toBe(30);
    expect(attemptStepGrant(45, 4)).toBe(30);
    expect(attemptStepGrant(20, 4)).toBe(5);
    expect(attemptStepGrant(15, 3)).toBe(5);
    expect(attemptStepGrant(10, 2)).toBe(5);
    expect(attemptStepGrant(5, 1)).toBe(5);
    expect(attemptStepGrant(4, 1)).toBeNull();
  });

  it("labels Settings/Play provider badges", () => {
    expect(providerBadgeLabel("openrouter")).toBe("OpenRouter");
    expect(providerBadgeLabel("nvidia-nim")).toBe("NVIDIA NIM");
    expect(providerBadgeLabel("groq")).toBe("Groq");
    expect(providerBadgeLabel("google-gemini")).toBe("Google Gemini");
    expect(providerBadgeLabel("cloudflare-workers-ai")).toBe(
      "Cloudflare Workers AI",
    );
    expect(providerBadgeLabel("mistral")).toBe("Mistral");
    expect(providerBadgeLabel("ibm-watsonx")).toBe("IBM watsonx.ai");
    expect(providerBadgeLabel("aion")).toBe("Aion");
    expect(providerBadgeLabel("huggingface")).toBe("Hugging Face");
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

  it("retains only bounded retry-after telemetry", () => {
    expect(
      retryAfterSecondsFromTerminal({
        kind: "coded_provider_error",
        code: "provider_rate_limited",
        message: "429",
        retryAfterSeconds: 86_400,
      }),
    ).toBe(86_400);
    expect(
      retryAfterSecondsFromTerminal({
        kind: "generic_error",
        message: "boom",
        retryAfterSeconds: 86_401,
      }),
    ).toBeUndefined();
  });
});

describe("orchestrateFallbackTurn", () => {
  const baseOpts = {
    queue: buildFallbackQueue("", NEWEST_FIRST_CATALOG),
    turnStartedAtMs: 0,
    aiTimeoutSeconds: 120,
    maxStepsTotal: 50,
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
    expect(result.posts[0]?.maxStepsRemaining).toBe(40);
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
    // Each lane is capped at the five-step tail reserve. The provider reports
    // ten actual requests anyway, so accounting charges actual usage safely.
    expect(calls).toBe(2);
    expect(grantedSteps).toEqual([10, 5]);
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
      20, 20, 20,
    ]);
    expect(result.stopReason).toBe("queue_exhausted");
    expect(result.providerRequestsUsed).toBe(6);
  });

  it("defensively caps a raw caller queue at three lanes", async () => {
    const rawQueue = [
      ...NEWEST_FIRST_CATALOG,
      { provider: "openrouter", model_id: "extra/sixth:free" },
    ];
    const runStream = vi.fn(async () => CODED_UNAVAILABLE);
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      queue: rawQueue,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(3);
    expect(result.posts).toHaveLength(3);
    expect(result.posts.map((post) => post.pair)).toEqual(
      NEWEST_FIRST_CATALOG.slice(0, 3),
    );
    expect(result.stopReason).toBe("queue_exhausted");
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
      nowMs = 60_000;
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

  it("sums every attempt including the finally-successful one before returning", async () => {
    const runStream = vi.fn(
      async (request: {
        attemptIndex: number;
      }): Promise<AiMoveStreamTerminal> =>
        request.attemptIndex === 0
          ? {
              kind: "coded_provider_error",
              code: "provider_rate_limited",
              message: "429",
              providerRequestsUsed: 3,
            }
          : doneWith(4),
    );
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(2);
    expect(result.stopReason).toBe("done");
    expect(result.providerRequestsUsed).toBe(7);
    expect(result.lastTerminal).toEqual({
      kind: "done",
      data: {
        type: "done",
        ok: true,
        action: "place",
        provider_requests_used: 4,
        turn_provider_requests_used: 7,
      },
    });
  });

  it("does not double-count usage across retried pairs", async () => {
    const runStream = vi.fn(
      async (request: {
        attemptIndex: number;
      }): Promise<AiMoveStreamTerminal> => {
        if (request.attemptIndex === 0) {
          return {
            kind: "coded_provider_error",
            code: "provider_rate_limited",
            message: "429",
            providerRequestsUsed: 6,
          };
        }
        if (request.attemptIndex === 1) {
          return {
            kind: "coded_provider_error",
            code: "provider_unavailable",
            message: "down",
            providerRequestsUsed: 2,
          };
        }
        return doneWith(5);
      },
    );
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () => activeState(),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(3);
    expect(result.providerRequestsUsed).toBe(13);
    expect(result.posts.map((post) => post.maxStepsRemaining)).toEqual([
      40, 39, 39,
    ]);
    if (result.lastTerminal?.kind === "done") {
      expect(result.lastTerminal.data.turn_provider_requests_used).toBe(13);
      expect(result.lastTerminal.data.provider_requests_used).toBe(5);
    }
  });

  it("reconciles the unchanged turn before every later pair and never before the first", async () => {
    const events: string[] = [];
    const fetchGameState = vi.fn(async () => {
      events.push("reconcile");
      return activeState();
    });
    const runStream = vi.fn(
      async (request: {
        attemptIndex: number;
      }): Promise<AiMoveStreamTerminal> => {
        events.push(`stream-${request.attemptIndex}`);
        if (request.attemptIndex < 2) {
          return {
            kind: "coded_provider_error",
            code: "provider_rate_limited",
            message: "429",
            providerRequestsUsed: 1,
          };
        }
        return doneWith(1);
      },
    );
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState,
      runStream,
    });
    expect(events).toEqual([
      "stream-0",
      "reconcile",
      "stream-1",
      "reconcile",
      "stream-2",
    ]);
    expect(result.providerRequestsUsed).toBe(3);
    expect(result.stopReason).toBe("done");
  });

  it("can succeed only on lane three with two reconciliations and one terminal", async () => {
    const persisted: number[] = [];
    const fetchGameState = vi.fn(async () => activeState());
    const runStream = vi.fn(
      async (request: {
        attemptIndex: number;
      }): Promise<AiMoveStreamTerminal> => {
        if (request.attemptIndex < 2) {
          return {
            kind: "coded_provider_error",
            code: "provider_unavailable",
            message: "No endpoints found",
            providerRequestsUsed: request.attemptIndex + 1,
            retryAfterSeconds: request.attemptIndex === 1 ? 12 : undefined,
          };
        }
        persisted.push(request.attemptIndex);
        return doneWith(5);
      },
    );
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      now: () => 0,
      fetchGameState,
      runStream,
    });

    expect(runStream).toHaveBeenCalledTimes(3);
    expect(fetchGameState).toHaveBeenCalledTimes(2);
    expect(persisted).toEqual([2]);
    expect(result.stopReason).toBe("done");
    expect(result.posts.map((post) => post.timeoutSeconds)).toEqual([
      40, 60, 120,
    ]);
    expect(result.posts.map((post) => post.maxStepsRemaining)).toEqual([
      40, 40, 40,
    ]);
    expect(result.providerRequestsUsed).toBe(8);
    expect(result.retryAfterSeconds).toBe(12);
    expect(result.lastTerminal).toEqual({
      kind: "done",
      data: expect.objectContaining({
        provider_requests_used: 5,
        turn_provider_requests_used: 8,
        turn_retry_after_seconds: 12,
      }),
    });
  });

  it("stops before lane two when reconciliation observes a changed turn", async () => {
    const runStream = vi.fn(async () => CODED_UNAVAILABLE);
    const result = await orchestrateFallbackTurn({
      ...baseOpts,
      fetchGameState: async () => activeState({ move_count: 5 }),
      runStream,
    });
    expect(runStream).toHaveBeenCalledTimes(1);
    expect(result.stopReason).toBe("reconciliation");
  });
});
