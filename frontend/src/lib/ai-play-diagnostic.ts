/**
 * Provider-free AI-turn diagnostic helpers.
 *
 * Fake mode injects only getLanguageRuntime / generateText. Django HTTP,
 * fallback orchestration, and SSE consumption stay real.
 */

import { NextRequest } from "next/server";
import {
  MAX_FALLBACK_ATTEMPTS,
  aiMoveRequestBody,
  buildFallbackQueue,
  orchestrateFallbackTurn,
  type CatalogPair,
  type ReconciliationView,
} from "./ai-fallback";
import {
  consumeAIStream,
  type AiMoveStreamTerminal,
} from "./ai-move-stream";
import { asAiCompletionSource, type AiCompletionSource } from "./types";

export const LIVE_SENTINEL = "LIBRETILES_AI_PLAY_LIVE";
export const COMPLETION_SOURCES: readonly AiCompletionSource[] = [
  "provider_candidate",
  "backend_ranked_candidate",
  "repair_candidate",
  "backend_witness_rescue",
  "genuine_no_move_exchange",
  "genuine_no_move_pass",
];

export type QueueMode = "selected-only" | "catalog-fallback";
export type FakeScript = "noop_rescue" | "drop_done" | "generic_unchanged" | "validate_scripted";
export type DiagnosticRuntimeMode = "fake" | "live";
export type DiagnosticDriver = "fake" | "live";

export const SHIPPED_PROVIDER_ORIGINS: readonly string[] = [
  "https://openrouter.ai",
  "https://integrate.api.nvidia.com",
];

export type DiagnosticQueueInput = {
  provider: string;
  modelId: string;
  queueMode: QueueMode;
  catalog: CatalogPair[];
};

export type AttemptObservation = {
  provider: string;
  model_id: string;
  timeout_seconds: number;
  step_grant: number;
  provider_requests_used: number;
};

export type TerminalObservation = {
  terminal_kind: AiMoveStreamTerminal["kind"];
  action: string | null;
  completion_source: AiCompletionSource | null;
  probe_status: string | null;
  repair_attempted: boolean | null;
  terminal_cause: string | null;
  formed_words: string[];
  score: number;
  placements: Array<Record<string, unknown>>;
  attempts: AttemptObservation[];
  queue: CatalogPair[];
  queue_length: number;
  turn_provider_requests_used: number;
  unresolved_in_flight: number;
  lost_terminal: boolean;
  coded_provider_error: boolean;
  external_provider_invocations: number;
  backend_origins: string[];
  foreign_origins: string[];
  executed_runtime_mode?: DiagnosticRuntimeMode;
  driver?: DiagnosticDriver;
  sentinel_present?: boolean;
};

const SECRET_KEY_FRAGMENTS = [
  "authorization",
  "token",
  "secret",
  "password",
  "api_key",
  "apikey",
  "bearer",
  "cookie",
  "prompt",
  "raw_body",
  "env",
];

export function liveOptInEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env[LIVE_SENTINEL] === "1";
}

export function buildDiagnosticQueue(input: DiagnosticQueueInput): CatalogPair[] {
  const requested: CatalogPair = {
    provider: input.provider,
    model_id: input.modelId,
  };
  if (input.queueMode === "selected-only") {
    return [requested];
  }
  const catalog = input.catalog.some(
    (row) => row.provider === requested.provider && row.model_id === requested.model_id,
  )
    ? input.catalog
    : [requested, ...input.catalog];
  return buildFallbackQueue(input.modelId, catalog).slice(0, MAX_FALLBACK_ATTEMPTS);
}

export function originOf(input: RequestInfo | URL): string {
  const raw =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input instanceof Request
          ? input.url
          : String(input);
  try {
    return new URL(raw).origin;
  } catch {
    return raw;
  }
}

export function derivedExternalProviderInvocations(
  providerOrigins: readonly string[],
): number {
  return providerOrigins.length;
}

export function installFetchGuard(
  allowedOrigin: string,
  options?: {
    mode?: DiagnosticRuntimeMode;
    providerOrigins?: readonly string[];
  },
): {
  backend: string[];
  foreign: string[];
  provider: string[];
  restore: () => void;
} {
  const mode: DiagnosticRuntimeMode = options?.mode ?? "fake";
  const providerOrigins = [...(options?.providerOrigins ?? SHIPPED_PROVIDER_ORIGINS)];
  const backend: string[] = [];
  const foreign: string[] = [];
  const provider: string[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const origin = originOf(input);
    if (origin === allowedOrigin) {
      backend.push(origin);
      return original(input, init);
    }
    if (mode === "live" && providerOrigins.includes(origin)) {
      provider.push(origin);
      return original(input, init);
    }
    foreign.push(origin);
    return Promise.reject(
      new Error(
        mode === "live"
          ? `diagnostic live mode blocked origin ${origin}`
          : `diagnostic fake mode blocked foreign origin ${origin}`,
      ),
    );
  }) as typeof fetch;
  return {
    backend,
    foreign,
    provider,
    restore: () => {
      globalThis.fetch = original;
    },
  };
}

function dropDoneEvents(body: ReadableStream<Uint8Array> | null): ReadableStream<Uint8Array> | null {
  if (!body) return body;
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buffer = "";
  return body.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        buffer += decoder.decode(chunk, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const json = JSON.parse(line.slice(6)) as { type?: string };
              if (json.type === "done") continue;
            } catch {
              /* keep malformed lines */
            }
          }
          controller.enqueue(encoder.encode(`${line}\n`));
        }
      },
      flush(controller) {
        if (!buffer.trim()) return;
        if (buffer.startsWith("data: ")) {
          try {
            const json = JSON.parse(buffer.slice(6)) as { type?: string };
            if (json.type === "done") return;
          } catch {
            /* keep */
          }
        }
        controller.enqueue(encoder.encode(buffer));
      },
    }),
  );
}

export function stripDoneEvent(response: Response): Response {
  return new Response(dropDoneEvents(response.body), {
    status: response.status,
    headers: response.headers,
  });
}

function redactValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactValue);
  if (typeof value !== "object" || value === null) return value;
  const result: Record<string, unknown> = {};
  for (const [key, inner] of Object.entries(value)) {
    const lowered = key.toLowerCase();
    if (SECRET_KEY_FRAGMENTS.some((fragment) => lowered.includes(fragment))) continue;
    if (
      typeof inner === "string" &&
      (inner.startsWith("Bearer ") || inner.includes("/home/") || inner.includes("/Users/"))
    ) {
      continue;
    }
    result[key] = redactValue(inner);
  }
  return result;
}

function wordsFromUnknown(value: unknown): string[] {
  if (typeof value === "string" && value) return [value];
  if (!Array.isArray(value)) return [];
  const words: string[] = [];
  for (const item of value) {
    if (typeof item === "string" && item) words.push(item);
    else if (item && typeof item === "object" && typeof (item as { word?: unknown }).word === "string") {
      words.push((item as { word: string }).word);
    }
  }
  return words;
}

function placementsFromUnknown(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is Record<string, unknown> =>
      typeof item === "object" && item !== null && !Array.isArray(item),
  );
}

export function serializeTerminalObservation(input: {
  terminal: AiMoveStreamTerminal | null;
  attempts: AttemptObservation[];
  queue: CatalogPair[];
  turnProviderRequestsUsed: number;
  lostTerminal: boolean;
  externalProviderInvocations: number;
  backendOrigins: string[];
  foreignOrigins: string[];
  executedRuntimeMode?: DiagnosticRuntimeMode;
  driver?: DiagnosticDriver;
  sentinelPresent?: boolean;
}): TerminalObservation {
  const terminal = input.terminal;
  const data =
    terminal?.kind === "done" ? (terminal.data as Record<string, unknown>) : {};
  const telemetry =
    terminal && "telemetry" in terminal ? terminal.telemetry : undefined;
  const completionSource =
    asAiCompletionSource(data.completion_source) ??
    telemetry?.completionSource ??
    null;
  const probeStatus =
    typeof data.probe_status === "string"
      ? data.probe_status
      : (telemetry?.probeStatus ?? null);
  const terminalCause =
    typeof data.terminal_cause === "string"
      ? data.terminal_cause
      : (telemetry?.terminalCause ?? null);
  const repairAttempted =
    typeof data.repair_attempted === "boolean"
      ? data.repair_attempted
      : (telemetry?.repairAttempted ?? null);
  const action = typeof data.action === "string" ? data.action : null;
  const formedWords = wordsFromUnknown(data.words ?? data.allWords ?? data.best_word);
  const score =
    typeof data.best_score === "number"
      ? data.best_score
      : typeof data.points === "number"
        ? data.points
        : typeof data.score === "number"
          ? data.score
          : 0;
  const observation: TerminalObservation = {
    terminal_kind: terminal?.kind ?? "no_terminal",
    action,
    completion_source: completionSource,
    probe_status: probeStatus,
    repair_attempted: repairAttempted,
    terminal_cause: terminalCause,
    formed_words: formedWords,
    score,
    placements: placementsFromUnknown(data.placements),
    attempts: input.attempts,
    queue: input.queue,
    queue_length: input.queue.length,
    turn_provider_requests_used: input.turnProviderRequestsUsed,
    unresolved_in_flight: 0,
    lost_terminal: input.lostTerminal,
    coded_provider_error: terminal?.kind === "coded_provider_error",
    external_provider_invocations: input.externalProviderInvocations,
    backend_origins: [...new Set(input.backendOrigins)],
    foreign_origins: [...new Set(input.foreignOrigins)],
  };
  if (input.executedRuntimeMode) {
    observation.executed_runtime_mode = input.executedRuntimeMode;
  }
  if (input.driver) {
    observation.driver = input.driver;
  }
  if (typeof input.sentinelPresent === "boolean") {
    observation.sentinel_present = input.sentinelPresent;
  }
  return redactValue(observation) as TerminalObservation;
}

async function fetchCatalog(backendUrl: string): Promise<CatalogPair[]> {
  const response = await fetch(`${backendUrl}/api/catalog/models/`, { cache: "no-store" });
  if (!response.ok) return [];
  const data: unknown = await response.json();
  if (!Array.isArray(data)) return [];
  const rows: CatalogPair[] = [];
  for (const item of data) {
    if (!item || typeof item !== "object") continue;
    const record = item as { provider?: unknown; model_id?: unknown };
    if (typeof record.provider === "string" && typeof record.model_id === "string") {
      rows.push({ provider: record.provider, model_id: record.model_id });
    }
  }
  return rows;
}

async function fetchReconciliation(
  backendUrl: string,
  gameId: string,
  token: string,
): Promise<ReconciliationView | null> {
  const response = await fetch(`${backendUrl}/api/game/${gameId}/`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) return null;
  const data: unknown = await response.json();
  if (!data || typeof data !== "object") return null;
  const record = data as Record<string, unknown>;
  return {
    game_id: typeof record.game_id === "string" ? record.game_id : gameId,
    move_count: typeof record.move_count === "number" ? record.move_count : 0,
    status: typeof record.status === "string" ? record.status : "active",
    current_turn_slot:
      typeof record.current_turn_slot === "number" ? record.current_turn_slot : null,
    game_over: record.game_over === true,
  };
}

export async function runDiagnosticTurn(opts: {
  post: (request: NextRequest) => Promise<Response>;
  backendUrl: string;
  gameId: string;
  token: string;
  provider: string;
  modelId: string;
  timeoutSeconds: number;
  maxSteps: number;
  queueMode: QueueMode;
  script: FakeScript;
  scriptedPlacements?: Array<Record<string, unknown>>;
  backendOrigins?: string[];
  foreignOrigins?: string[];
  providerOrigins?: string[];
  executedRuntimeMode?: DiagnosticRuntimeMode;
  driver?: DiagnosticDriver;
}): Promise<TerminalObservation> {
  const providerOrigins = opts.providerOrigins ?? [];
  const invocations = derivedExternalProviderInvocations(providerOrigins);
  if (opts.script === "generic_unchanged") {
    return serializeTerminalObservation({
      terminal: { kind: "generic_error", message: "AI move failed" },
      attempts: [],
      queue: [{ provider: opts.provider, model_id: opts.modelId }],
      turnProviderRequestsUsed: 0,
      lostTerminal: false,
      externalProviderInvocations: invocations,
      backendOrigins: [],
      foreignOrigins: [],
      executedRuntimeMode: opts.executedRuntimeMode,
      driver: opts.driver,
      sentinelPresent: liveOptInEnabled(),
    });
  }

  const catalog = await fetchCatalog(opts.backendUrl);
  const queue = buildDiagnosticQueue({
    provider: opts.provider,
    modelId: opts.modelId,
    queueMode: opts.queueMode,
    catalog,
  });
  const latest = await fetchReconciliation(opts.backendUrl, opts.gameId, opts.token);
  const moveCount = latest?.move_count ?? 0;
  const result = await orchestrateFallbackTurn({
    queue,
    turnStartedAtMs: Date.now(),
    aiTimeoutSeconds: opts.timeoutSeconds,
    maxStepsTotal: opts.maxSteps,
    now: () => Date.now(),
    anchor: { gameId: opts.gameId, moveCount, aiSlot: 1 },
    fetchGameState: () => fetchReconciliation(opts.backendUrl, opts.gameId, opts.token),
    runStream: async (request) => {
      const body = aiMoveRequestBody({
        gameId: opts.gameId,
        token: opts.token,
        preferenceModelId: opts.modelId,
        runtimeModelId: request.pair.model_id,
        timeout: request.timeoutSeconds,
        maxSteps: request.maxStepsRemaining,
      });
      const req = new NextRequest("http://localhost/api/ai/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      let response = await opts.post(req);
      if (opts.script === "drop_done") {
        response = stripDoneEvent(response);
      }
      if (!(response.headers.get("content-type") ?? "").includes("text/event-stream")) {
        return { kind: "generic_error", message: "expected SSE from move route" };
      }
      return consumeAIStream(response, {
        onCandidate: () => {},
        onStatus: () => {},
      });
    },
  });

  const attempts: AttemptObservation[] = result.posts.map((post) => ({
    provider: post.pair.provider,
    model_id: post.pair.model_id,
    timeout_seconds: post.timeoutSeconds,
    step_grant: post.maxStepsRemaining,
    provider_requests_used:
      post === result.posts[result.posts.length - 1]
        ? result.providerRequestsUsed
        : 0,
  }));
  const lostTerminal = opts.script === "drop_done";
  const observation = serializeTerminalObservation({
    terminal: result.lastTerminal,
    attempts,
    queue,
    turnProviderRequestsUsed: result.providerRequestsUsed,
    lostTerminal,
    externalProviderInvocations: invocations,
    backendOrigins: opts.backendOrigins ?? [],
    foreignOrigins: opts.foreignOrigins ?? [],
    executedRuntimeMode: opts.executedRuntimeMode,
    driver: opts.driver,
    sentinelPresent: liveOptInEnabled(),
  });
  if (lostTerminal && !observation.terminal_cause) {
    observation.terminal_cause = "lost_sse_done";
  }
  return observation;
}
