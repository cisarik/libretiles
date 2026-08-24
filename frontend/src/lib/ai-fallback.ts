import { findCuratedPair } from "./ai-runtimes";
import type { AiMoveStreamTerminal } from "./ai-move-stream";

export const MIN_ATTEMPT_TIMEOUT_SECONDS = 15;
export const MAX_FALLBACK_ATTEMPTS = 3;

export type CatalogPair = {
  provider: string;
  model_id: string;
};

export type FallbackStopReason =
  | "done"
  | "generic_error"
  | "no_terminal"
  | "queue_exhausted"
  | "deadline"
  | "reconciliation"
  | "empty_queue";

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
 * Catalog rows are already eligibility-filtered. Queue at most three distinct
 * `(provider, model_id)` pairs: selected, then unused-provider diversity, then
 * unused providers or the next unused catalog models.
 */
export function buildFallbackQueue(
  selectedModelId: string,
  catalogRows: CatalogPair[],
): CatalogPair[] {
  const queue: CatalogPair[] = [];
  const used = new Set<string>();
  const usedProviders = new Set<string>();

  const tryAppend = (row: CatalogPair): boolean => {
    const key = pairKey(row);
    if (used.has(key)) return false;
    used.add(key);
    usedProviders.add(row.provider);
    queue.push({ provider: row.provider, model_id: row.model_id });
    return true;
  };

  const selected = catalogRows.find((row) => row.model_id === selectedModelId);
  if (selected) tryAppend(selected);

  const appendUnusedProvider = (): boolean => {
    for (const row of catalogRows) {
      if (used.has(pairKey(row))) continue;
      if (usedProviders.has(row.provider)) continue;
      return tryAppend(row);
    }
    return false;
  };

  const appendNextUnused = (): boolean => {
    for (const row of catalogRows) {
      if (used.has(pairKey(row))) continue;
      return tryAppend(row);
    }
    return false;
  };

  if (queue.length < MAX_FALLBACK_ATTEMPTS) {
    appendUnusedProvider();
  }

  while (queue.length < MAX_FALLBACK_ATTEMPTS) {
    if (appendUnusedProvider()) continue;
    if (!appendNextUnused()) break;
  }

  return queue;
}

/** Catalog fetch failed: only the already-resolved selected id, no static fill. */
export function fallbackQueueForCatalogFailure(
  selectedModelId: string,
): CatalogPair[] {
  const curated = findCuratedPair(selectedModelId);
  return [
    {
      provider: curated?.provider ?? "openrouter",
      model_id: selectedModelId,
    },
  ];
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
 * Sequential one-turn fallback. Attempt 2+ never POSTs unless Django state
 * still matches the turn anchor.
 */
export async function orchestrateFallbackTurn(opts: {
  queue: CatalogPair[];
  turnStartedAtMs: number;
  aiTimeoutSeconds: number;
  now: () => number;
  anchor: TurnAnchor;
  fetchGameState: () => Promise<ReconciliationView | null>;
  runStream: (request: FallbackAttemptRequest) => Promise<AiMoveStreamTerminal>;
}): Promise<{
  posts: FallbackAttemptRequest[];
  stopReason: FallbackStopReason;
  lastTerminal: AiMoveStreamTerminal | null;
}> {
  const posts: FallbackAttemptRequest[] = [];
  let lastTerminal: AiMoveStreamTerminal | null = null;

  if (opts.queue.length === 0) {
    return { posts, stopReason: "empty_queue", lastTerminal };
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
        return { posts, stopReason: "deadline", lastTerminal };
      }
      const latest = await opts.fetchGameState();
      reconciliationAllowsRetry = gameStateAllowsRetry(opts.anchor, latest);
    }

    const decision = decideNextFallbackAttempt({
      attemptIndex,
      queueLength: opts.queue.length,
      previous: lastTerminal,
      remainingSeconds,
      reconciliationAllowsRetry,
    });
    if (decision.action === "stop") {
      return { posts, stopReason: decision.reason, lastTerminal };
    }

    const request: FallbackAttemptRequest = {
      pair: opts.queue[attemptIndex],
      attemptIndex,
      timeoutSeconds: decision.timeoutSeconds,
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
      return { posts, stopReason: immediateStop, lastTerminal };
    }
  }

  return { posts, stopReason: "queue_exhausted", lastTerminal };
}
