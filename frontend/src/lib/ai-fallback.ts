import type { AiMoveStreamTerminal } from "./ai-move-stream";
import {
  NVIDIA_NIM_MODEL_ID,
  NVIDIA_NIM_PROVIDER,
  OPENROUTER_PROVIDER,
  isOpenRouterFreeId,
  playableCatalogPairs,
  type CatalogPair,
} from "./model-catalog";

export const MIN_ATTEMPT_TIMEOUT_SECONDS = 15;
export const MAX_FALLBACK_ATTEMPTS = 3;
/** An attempt shorter than this cannot complete a meaningful tool loop. */
export const MIN_ATTEMPT_STEPS = 5;

export type { CatalogPair };

export type FallbackStopReason =
  | "done"
  | "generic_error"
  | "no_terminal"
  | "queue_exhausted"
  | "deadline"
  | "reconciliation"
  | "empty_queue"
  | "budget_exhausted";

export type TurnAnchor = {
  gameId: string;
  moveCount: number;
  aiSlot: number;
};

export type ReconciliationView = {
  game_id: string;
  move_count: number;
  status: string;
  current_turn_slot: number | null;
  game_over: boolean;
};

export type FallbackAttemptRequest = {
  pair: CatalogPair;
  attemptIndex: number;
  timeoutSeconds: number;
  /** Remaining whole-turn provider-call budget granted to this attempt. */
  maxStepsRemaining: number;
};

function pairKey(pair: CatalogPair): string {
  return `${pair.provider}\0${pair.model_id}`;
}

export function providerBadgeLabel(provider: string): string {
  if (provider === "nvidia-nim") return "NVIDIA NIM";
  if (provider === "openrouter") return "OpenRouter";
  return provider;
}

export function aiMoveRequestBody(input: {
  gameId: string;
  token: string;
  preferenceModelId: string;
  runtimeModelId: string;
  timeout: number;
  maxSteps: number;
}): {
  game_id: string;
  token: string;
  model_id: string;
  runtime_model_id: string;
  timeout: number;
  max_steps: number;
} {
  return {
    game_id: input.gameId,
    token: input.token,
    model_id: input.preferenceModelId,
    runtime_model_id: input.runtimeModelId,
    timeout: input.timeout,
    max_steps: input.maxSteps,
  };
}

/**
 * One shared queue for Play and Judge. A valid explicit preference is attempt
 * 1; remaining attempts follow untouched catalog order (newest-first). Distinct
 * pairs only, capped at MAX_FALLBACK_ATTEMPTS.
 */
export function buildFallbackQueue(
  selectedModelId: string | null | undefined,
  catalogRows: CatalogPair[],
): CatalogPair[] {
  const rows = playableCatalogPairs(catalogRows);
  const selected =
    selectedModelId
      ? rows.find((row) => row.model_id === selectedModelId)
      : undefined;

  const queue: CatalogPair[] = [];
  const used = new Set<string>();
  for (const row of selected ? [selected, ...rows] : rows) {
    const key = pairKey(row);
    if (used.has(key)) continue;
    used.add(key);
    queue.push({ provider: row.provider, model_id: row.model_id });
    if (queue.length >= MAX_FALLBACK_ATTEMPTS) break;
  }
  return queue;
}

/**
 * Catalog fetch failed: only the already-resolved selected id may be tried,
 * and only when it is structurally playable. Never invent a static list.
 */
export function fallbackQueueForCatalogFailure(
  selectedModelId: string,
): CatalogPair[] {
  if (selectedModelId === NVIDIA_NIM_MODEL_ID) {
    return [{ provider: NVIDIA_NIM_PROVIDER, model_id: selectedModelId }];
  }
  if (isOpenRouterFreeId(selectedModelId)) {
    return [{ provider: OPENROUTER_PROVIDER, model_id: selectedModelId }];
  }
  return [];
}

export function remainingTimeoutSeconds(
  turnStartedAtMs: number,
  aiTimeoutSeconds: number,
  nowMs: number,
): number {
  return Math.floor(aiTimeoutSeconds - (nowMs - turnStartedAtMs) / 1000);
}

export function canStartAttempt(remainingSeconds: number): boolean {
  return remainingSeconds >= MIN_ATTEMPT_TIMEOUT_SECONDS;
}

export function gameStateAllowsRetry(
  anchor: TurnAnchor,
  latest: ReconciliationView | null,
): boolean {
  if (!latest) return false;
  if (latest.game_id !== anchor.gameId) return false;
  if (latest.move_count !== anchor.moveCount) return false;
  if (latest.status !== "active") return false;
  if (latest.current_turn_slot !== anchor.aiSlot) return false;
  if (latest.game_over) return false;
  return true;
}

/** Whole-turn provider-call usage reported by a terminal. */
export function providerRequestsUsedFromTerminal(
  terminal: AiMoveStreamTerminal | null,
): number {
  if (!terminal) return 0;
  if (terminal.kind === "done") {
    const used = terminal.data.provider_requests_used;
    return typeof used === "number" && Number.isFinite(used) && used >= 0
      ? Math.floor(used)
      : 0;
  }
  if (
    terminal.kind === "coded_provider_error" ||
    terminal.kind === "generic_error"
  ) {
    const used = terminal.providerRequestsUsed;
    return typeof used === "number" && Number.isFinite(used) && used >= 0
      ? Math.floor(used)
      : 0;
  }
  return 0;
}

export function decideNextFallbackAttempt(input: {
  attemptIndex: number;
  queueLength: number;
  previous: AiMoveStreamTerminal | null;
  remainingSeconds: number;
  reconciliationAllowsRetry: boolean | null;
}): { action: "post"; timeoutSeconds: number } | { action: "stop"; reason: FallbackStopReason } {
  if (input.queueLength === 0) {
    return { action: "stop", reason: "empty_queue" };
  }
  if (input.attemptIndex >= input.queueLength) {
    return { action: "stop", reason: "queue_exhausted" };
  }
  if (input.previous) {
    if (input.previous.kind === "done") {
      return { action: "stop", reason: "done" };
    }
    if (input.previous.kind === "generic_error") {
      return { action: "stop", reason: "generic_error" };
    }
    if (input.previous.kind === "no_terminal") {
      return { action: "stop", reason: "no_terminal" };
    }
  }
  if (!canStartAttempt(input.remainingSeconds)) {
    return { action: "stop", reason: "deadline" };
  }
  if (input.attemptIndex > 0 && !input.reconciliationAllowsRetry) {
    return { action: "stop", reason: "reconciliation" };
  }
  return { action: "post", timeoutSeconds: input.remainingSeconds };
}

function stopReasonFromTerminal(
  terminal: AiMoveStreamTerminal,
): FallbackStopReason | null {
  if (terminal.kind === "done") return "done";
  if (terminal.kind === "generic_error") return "generic_error";
  if (terminal.kind === "no_terminal") return "no_terminal";
  return null;
}

/**
 * Sequential one-turn fallback with one shared provider-call budget across
 * attempts. Attempt 2+ never POSTs unless Django state still matches the
 * turn anchor, the deadline allows it, and budget remains.
 */
export async function orchestrateFallbackTurn(opts: {
  queue: CatalogPair[];
  turnStartedAtMs: number;
  aiTimeoutSeconds: number;
  /** Whole-turn provider-call budget shared by every fallback attempt. */
  maxStepsTotal: number;
  now: () => number;
  anchor: TurnAnchor;
  fetchGameState: () => Promise<ReconciliationView | null>;
  runStream: (request: FallbackAttemptRequest) => Promise<AiMoveStreamTerminal>;
}): Promise<{
  posts: FallbackAttemptRequest[];
  stopReason: FallbackStopReason;
  lastTerminal: AiMoveStreamTerminal | null;
  providerRequestsUsed: number;
}> {
  const posts: FallbackAttemptRequest[] = [];
  let lastTerminal: AiMoveStreamTerminal | null = null;
  let providerRequestsUsed = 0;
  let remainingSteps = Math.max(Math.floor(opts.maxStepsTotal), 0);

  if (opts.queue.length === 0) {
    return { posts, stopReason: "empty_queue", lastTerminal, providerRequestsUsed };
  }

  for (let attemptIndex = 0; attemptIndex < opts.queue.length; attemptIndex += 1) {
    const remainingSeconds = remainingTimeoutSeconds(
      opts.turnStartedAtMs,
      opts.aiTimeoutSeconds,
      opts.now(),
    );
    let reconciliationAllowsRetry: boolean | null = null;
    if (attemptIndex > 0) {
      if (!canStartAttempt(remainingSeconds)) {
        return {
          posts,
          stopReason: "deadline",
          lastTerminal,
          providerRequestsUsed,
        };
      }
      const latest = await opts.fetchGameState();
      reconciliationAllowsRetry = gameStateAllowsRetry(opts.anchor, latest);
    }
    if (attemptIndex > 0 && remainingSteps < MIN_ATTEMPT_STEPS) {
      return {
        posts,
        stopReason: "budget_exhausted",
        lastTerminal,
        providerRequestsUsed,
      };
    }

    const decision = decideNextFallbackAttempt({
      attemptIndex,
      queueLength: opts.queue.length,
      previous: lastTerminal,
      remainingSeconds,
      reconciliationAllowsRetry,
    });
    if (decision.action === "stop") {
      return {
        posts,
        stopReason: decision.reason,
        lastTerminal,
        providerRequestsUsed,
      };
    }

    const request: FallbackAttemptRequest = {
      pair: opts.queue[attemptIndex],
      attemptIndex,
      timeoutSeconds: decision.timeoutSeconds,
      maxStepsRemaining: remainingSteps,
    };
    posts.push(request);

    try {
      lastTerminal = await opts.runStream(request);
    } catch (error) {
      lastTerminal = {
        kind: "generic_error",
        message: error instanceof Error ? error.message : "AI move failed",
      };
    }

    const immediateStop = stopReasonFromTerminal(lastTerminal);
    if (immediateStop) {
      return { posts, stopReason: immediateStop, lastTerminal, providerRequestsUsed };
    }

    // A failed stream without reported usage conservatively charges the
    // minimum viable attempt so unaccounted provider HTTP cannot spin forever.
    const reported = providerRequestsUsedFromTerminal(lastTerminal);
    const charged =
      lastTerminal?.kind === "done"
        ? reported
        : Math.max(reported, MIN_ATTEMPT_STEPS);
    remainingSteps = Math.max(remainingSteps - charged, 0);
    providerRequestsUsed += reported;
  }

  return { posts, stopReason: "queue_exhausted", lastTerminal, providerRequestsUsed };
}
