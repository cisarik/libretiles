export type InspectionPlacement = {
  row: number;
  col: number;
  letter: string;
  blank_as?: string;
};

export type InspectionTraceEvent = {
  ordinal: number;
  elapsed_ms: number;
  phase: "search" | "repair" | "finishMove";
  tool: "validateMove" | "finishMove" | "phase";
  placements?: InspectionPlacement[];
  words?: string[];
  valid?: boolean;
  rejection_code?: string;
  score?: number;
  ready?: true;
  marker?: string;
  incomplete?: true;
};

export type InspectionTraceAttempt = {
  attempt_index: number;
  provider?: string;
  model_id?: string;
  latency_ms?: number;
  provider_requests_used?: number;
  outcome?: string;
  events: InspectionTraceEvent[];
  truncated?: true;
  omitted_event_count?: number;
};

export type InspectionTrace = {
  version: 1;
  attempts: InspectionTraceAttempt[];
  truncated?: true;
};

const MAX_ATTEMPTS = 3;
const MAX_EVENTS = 64;
const MAX_ATTEMPT_BYTES = 32 * 1024;
const MAX_TRACE_BYTES = 96 * 1024;
const MAX_TOKEN_LENGTH = 16;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function boundedString(value: unknown, max = 200): string | undefined {
  return typeof value === "string" && value.length > 0 && value.length <= max
    ? value
    : undefined;
}

function boundedCounter(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? Math.floor(value)
    : undefined;
}

function sanitizePlacement(value: unknown): InspectionPlacement | null {
  if (!isRecord(value)) return null;
  const row = boundedCounter(value.row);
  const col = boundedCounter(value.col);
  const letter = boundedString(value.letter, MAX_TOKEN_LENGTH);
  if (row === undefined || col === undefined || row > 14 || col > 14 || !letter) {
    return null;
  }
  const blankAs = boundedString(value.blank_as ?? value.blankAs, MAX_TOKEN_LENGTH);
  if ((letter === "?") !== Boolean(blankAs)) return null;
  return { row, col, letter, ...(blankAs ? { blank_as: blankAs } : {}) };
}

function sanitizeEvent(value: unknown): InspectionTraceEvent | null {
  if (!isRecord(value)) return null;
  const ordinal = boundedCounter(value.ordinal);
  const elapsed = boundedCounter(value.elapsed_ms);
  const phase = value.phase;
  const tool = value.tool;
  if (
    ordinal === undefined ||
    elapsed === undefined ||
    !["search", "repair", "finishMove"].includes(String(phase)) ||
    !["validateMove", "finishMove", "phase"].includes(String(tool))
  ) {
    return null;
  }
  const event: InspectionTraceEvent = {
    ordinal,
    elapsed_ms: elapsed,
    phase: phase as InspectionTraceEvent["phase"],
    tool: tool as InspectionTraceEvent["tool"],
  };
  if (event.tool === "validateMove") {
    event.placements = Array.isArray(value.placements)
      ? value.placements.slice(0, 7).map(sanitizePlacement).filter((item): item is InspectionPlacement => item !== null)
      : [];
    if (typeof value.valid === "boolean") event.valid = value.valid;
    if (Array.isArray(value.words)) {
      event.words = value.words
        .slice(0, 8)
        .map((word) => typeof word === "string" ? word : isRecord(word) ? word.word : null)
        .filter((word): word is string => typeof word === "string" && word.length <= 80);
    }
    const rejection = boundedString(value.rejection_code, 80);
    if (rejection) event.rejection_code = rejection;
    const score = boundedCounter(value.score);
    if (score !== undefined) event.score = score;
  }
  if (event.tool === "finishMove" && value.ready === true) event.ready = true;
  const marker = boundedString(value.marker, 80);
  if (marker) event.marker = marker;
  if (value.incomplete === true) event.incomplete = true;
  return event;
}

function sanitizeAttempt(value: unknown): InspectionTraceAttempt | null {
  if (!isRecord(value)) return null;
  const attemptIndex = boundedCounter(value.attempt_index);
  if (attemptIndex === undefined || attemptIndex >= MAX_ATTEMPTS) return null;
  const rawEvents = Array.isArray(value.events) ? value.events : [];
  const attempt: InspectionTraceAttempt = {
    attempt_index: attemptIndex,
    events: rawEvents.slice(0, MAX_EVENTS).map(sanitizeEvent).filter((event): event is InspectionTraceEvent => event !== null),
  };
  const provider = boundedString(value.provider);
  const modelId = boundedString(value.model_id);
  const outcome = boundedString(value.outcome, 80);
  if (provider) attempt.provider = provider;
  if (modelId) attempt.model_id = modelId;
  if (outcome) attempt.outcome = outcome;
  for (const key of ["latency_ms", "provider_requests_used"] as const) {
    const counter = boundedCounter(value[key]);
    if (counter !== undefined) attempt[key] = counter;
  }
  const omitted = Math.max(rawEvents.length - MAX_EVENTS, 0);
  if (omitted > 0 || value.truncated === true) {
    attempt.truncated = true;
    attempt.omitted_event_count = omitted + (boundedCounter(value.omitted_event_count) ?? 0);
  }
  while (JSON.stringify(attempt).length > MAX_ATTEMPT_BYTES && attempt.events.length > 1) {
    attempt.events.splice(attempt.events.length - 2, 1);
    attempt.truncated = true;
    attempt.omitted_event_count = (attempt.omitted_event_count ?? 0) + 1;
  }
  return attempt;
}

export function sanitizeInspectionTrace(value: unknown): InspectionTrace | null {
  if (!isRecord(value) || value.version !== 1 || !Array.isArray(value.attempts)) return null;
  const attempts = value.attempts.slice(0, MAX_ATTEMPTS).map(sanitizeAttempt).filter((attempt): attempt is InspectionTraceAttempt => attempt !== null);
  const trace: InspectionTrace = { version: 1, attempts };
  if (value.attempts.length > MAX_ATTEMPTS || value.truncated === true) trace.truncated = true;
  while (JSON.stringify(trace).length > MAX_TRACE_BYTES && trace.attempts.length > 1) {
    trace.attempts.shift();
    trace.truncated = true;
  }
  return trace;
}

export function inspectionTraceFromTerminal(value: unknown): InspectionTrace | null {
  if (!isRecord(value)) return null;
  if (value.kind === "done" && isRecord(value.data)) {
    return sanitizeInspectionTrace(value.data.inspection_trace);
  }
  return sanitizeInspectionTrace(value.inspectionTrace);
}

export function createInspectionTraceCollector(input: {
  attemptIndex: number;
  previous?: unknown;
  startedAt?: number;
  now?: () => number;
}) {
  const previous = sanitizeInspectionTrace(input.previous);
  const startedAt = input.startedAt ?? Date.now();
  const now = input.now ?? Date.now;
  const events: InspectionTraceEvent[] = [];
  let omitted = 0;
  let phase: InspectionTraceEvent["phase"] = "search";

  function append(event: Omit<InspectionTraceEvent, "ordinal" | "elapsed_ms">) {
    const complete = { ordinal: events.length + omitted, elapsed_ms: Math.max(now() - startedAt, 0), ...event } as InspectionTraceEvent;
    if (events.length < MAX_EVENTS) events.push(complete);
    else omitted += 1;
    return complete.ordinal;
  }

  return {
    beginValidate(placements: unknown) {
      const ordinal = append({
        phase,
        tool: "validateMove",
        placements: Array.isArray(placements) ? placements.map(sanitizePlacement).filter((item): item is InspectionPlacement => item !== null).slice(0, 7) : [],
        incomplete: true,
      });
      return (result: unknown) => {
        const index = events.findIndex((event) => event.ordinal === ordinal);
        if (index < 0 || !isRecord(result)) return;
        const words = Array.isArray(result.words)
          ? result.words.map((word) => typeof word === "string" ? word : isRecord(word) ? word.word : null).filter((word): word is string => typeof word === "string").slice(0, 8)
          : [];
        const reasonCode = boundedString(result.reason_code ?? result.code, 80);
        events[index] = {
          ...events[index],
          valid: result.valid === true,
          words,
          ...(boundedCounter(result.total_score) !== undefined ? { score: boundedCounter(result.total_score) } : {}),
          ...(reasonCode ? { rejection_code: reasonCode } : {}),
        };
        delete events[index].incomplete;
      };
    },
    startRepair() {
      phase = "repair";
      append({ phase, tool: "phase", marker: "repair_start" });
    },
    finishMove() {
      phase = "finishMove";
      append({ phase, tool: "finishMove", ready: true });
    },
    snapshot(details: {
      provider?: string;
      modelId?: string;
      outcome?: string;
      providerRequestsUsed?: number;
    }): InspectionTrace {
      const attempt = sanitizeAttempt({
        attempt_index: input.attemptIndex,
        provider: details.provider,
        model_id: details.modelId,
        outcome: details.outcome,
        latency_ms: Math.max(now() - startedAt, 0),
        provider_requests_used: details.providerRequestsUsed,
        events,
        truncated: omitted > 0,
        omitted_event_count: omitted,
      });
      return sanitizeInspectionTrace({
        version: 1,
        attempts: [...(previous?.attempts ?? []), ...(attempt ? [attempt] : [])],
        truncated: previous?.truncated,
      }) ?? { version: 1, attempts: [] };
    },
  };
}
