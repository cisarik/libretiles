import type { AiMoveStreamTerminal } from "./ai-move-stream";
import {
  NVIDIA_NIM_MODEL_ID,
  NVIDIA_NIM_PROVIDER,
  OPENROUTER_PROVIDER,
  isOpenRouterFreeId,
  playableCatalogPairs,
  type CatalogPair,
} from "./model-catalog";
import { providerLabel } from "./provider-registry";

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
  /** Provider/IAM request budget granted to this attempt. */
  maxStepsRemaining: number;
};

function pairKey(pair: CatalogPair): string {
  return `${pair.provider}\0${pair.model_id}`;
}

export function providerBadgeLabel(provider: string): string {
  return providerLabel(provider);
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
  return Number.isFinite(remainingSeconds) && remainingSeconds > 0;
}

/** Divide the whole-turn deadline while still allowing a short final tail. */
export function attemptTimeoutSeconds(
  remainingSeconds: number,
  attemptsLeft: number,
): number {
  if (!canStartAttempt(remainingSeconds) || attemptsLeft < 1) return 0;
  const boundedRemaining = Math.floor(remainingSeconds);
  return Math.min(
    boundedRemaining,
    Math.max(
      MIN_ATTEMPT_TIMEOUT_SECONDS,
      Math.floor(boundedRemaining / attemptsLeft),
    ),
  );
}

/** Reserve five provider/IAM requests for every later fallback lane. */
export function attemptStepGrant(
  remainingSteps: number,
  attemptsLeft: number,
): number | null {
  const boundedRemaining = Math.max(Math.floor(remainingSteps), 0);
  if (boundedRemaining < MIN_ATTEMPT_STEPS || attemptsLeft < 1) return null;
  const grant = Math.max(
    MIN_ATTEMPT_STEPS,
    boundedRemaining - MIN_ATTEMPT_STEPS * (attemptsLeft - 1),
  );
  return Math.min(grant, boundedRemaining);
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

export function retryAfterSecondsFromTerminal(
  terminal: AiMoveStreamTerminal | null,
): number | undefined {
  if (!terminal) return undefined;
  const value =
    terminal.kind === "done"
      ? terminal.data.retry_after_seconds
      : terminal.kind === "coded_provider_error" || terminal.kind === "generic_error"
        ? terminal.retryAfterSeconds
        : undefined;
  return typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 86_400
    ? Math.floor(value)
    : undefined;
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
  const attemptsLeft = input.queueLength - input.attemptIndex;
  return {
    action: "post",
    timeoutSeconds: attemptTimeoutSeconds(input.remainingSeconds, attemptsLeft),
  };
}

function stopReasonFromTerminal(
  terminal: AiMoveStreamTerminal,
): FallbackStopReason | null {
  if (terminal.kind === "done") return "done";
  if (terminal.kind === "generic_error") return "generic_error";
  if (terminal.kind === "no_terminal") return "no_terminal";
  return null;
}

function stampTurnProviderRequests(
  terminal: AiMoveStreamTerminal | null,
  used: number,
  retryAfterSeconds?: number,
): AiMoveStreamTerminal | null {
  if (!terminal || terminal.kind !== "done") return terminal;
  return {
    kind: "done",
    data: {
      ...terminal.data,
      turn_provider_requests_used: used,
      ...(retryAfterSeconds === undefined
        ? {}
        : { turn_retry_after_seconds: retryAfterSeconds }),
    },
  };
}

/**
 * Charge one attempt against the shared whole-turn budget. Reported provider
 * HTTP is summed into `providerRequestsUsed` (including a finally-successful
 * `done`). Failed streams without usage still consume the minimum viable
 * attempt from remaining steps so a silent provider cannot spin forever.
 */
function chargeAttemptUsage(
  terminal: AiMoveStreamTerminal | null,
  remainingSteps: number,
  providerRequestsUsed: number,
): { remainingSteps: number; providerRequestsUsed: number } {
  const reported = providerRequestsUsedFromTerminal(terminal);
  const charged =
    terminal?.kind === "done" ? reported : Math.max(reported, MIN_ATTEMPT_STEPS);
  return {
    remainingSteps: Math.max(remainingSteps - charged, 0),
    providerRequestsUsed: providerRequestsUsed + reported,
  };
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
  retryAfterSeconds?: number;
}> {
  const posts: FallbackAttemptRequest[] = [];
  const queue = opts.queue.slice(0, MAX_FALLBACK_ATTEMPTS);
  let lastTerminal: AiMoveStreamTerminal | null = null;
  let providerRequestsUsed = 0;
  let retryAfterSeconds: number | undefined;
  let remainingSteps = Math.max(Math.floor(opts.maxStepsTotal), 0);

  if (queue.length === 0) {
    return {
      posts,
      stopReason: "empty_queue",
      lastTerminal,
      providerRequestsUsed,
      retryAfterSeconds,
    };
  }

  for (let attemptIndex = 0; attemptIndex < queue.length; attemptIndex += 1) {
    const remainingSeconds = remainingTimeoutSeconds(
      opts.turnStartedAtMs,
      opts.aiTimeoutSeconds,
      opts.now(),
    );
    const attemptsLeft = queue.length - attemptIndex;
    let reconciliationAllowsRetry: boolean | null = null;
    if (attemptIndex > 0) {
      if (!canStartAttempt(remainingSeconds)) {
        return {
          posts,
          stopReason: "deadline",
          lastTerminal,
          providerRequestsUsed,
          retryAfterSeconds,
        };
      }
      const latest = await opts.fetchGameState();
      reconciliationAllowsRetry = gameStateAllowsRetry(opts.anchor, latest);
    }
    const stepGrant = attemptStepGrant(remainingSteps, attemptsLeft);
    if (stepGrant === null) {
      return {
        posts,
        stopReason: "budget_exhausted",
        lastTerminal,
        providerRequestsUsed,
        retryAfterSeconds,
      };
    }

    const decision = decideNextFallbackAttempt({
      attemptIndex,
      queueLength: queue.length,
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
        retryAfterSeconds,
      };
    }

    const request: FallbackAttemptRequest = {
      pair: queue[attemptIndex],
      attemptIndex,
      timeoutSeconds: decision.timeoutSeconds,
      maxStepsRemaining: stepGrant,
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

    const charged = chargeAttemptUsage(
      lastTerminal,
      remainingSteps,
      providerRequestsUsed,
    );
    remainingSteps = charged.remainingSteps;
    providerRequestsUsed = charged.providerRequestsUsed;
    const attemptRetryAfter = retryAfterSecondsFromTerminal(lastTerminal);
    if (attemptRetryAfter !== undefined) {
      retryAfterSeconds = Math.max(retryAfterSeconds ?? 0, attemptRetryAfter);
    }
    lastTerminal = stampTurnProviderRequests(
      lastTerminal,
      providerRequestsUsed,
      retryAfterSeconds,
    );

    const immediateStop = lastTerminal
      ? stopReasonFromTerminal(lastTerminal)
      : null;
    if (immediateStop) {
      return {
        posts,
        stopReason: immediateStop,
        lastTerminal,
        providerRequestsUsed,
        retryAfterSeconds,
      };
    }
  }

  return {
    posts,
    stopReason: "queue_exhausted",
    lastTerminal,
    providerRequestsUsed,
    retryAfterSeconds,
  };
}
