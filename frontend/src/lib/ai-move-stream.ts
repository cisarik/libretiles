import {
  asAiCompletionSource,
  describeAiTurnTelemetry,
  type AICandidate,
  type AiTurnTelemetry,
} from "./types";

export const CODED_PROVIDER_ERROR_CODES = [
  "provider_auth_failed",
  "provider_rate_limited",
  "provider_unavailable",
] as const;

export type CodedProviderErrorCode = (typeof CODED_PROVIDER_ERROR_CODES)[number];

export type AiMoveStreamTerminal =
  | { kind: "done"; data: Record<string, unknown> }
  | {
      kind: "coded_provider_error";
      code: CodedProviderErrorCode;
      message: string;
      /** Provider model-step HTTP calls already spent inside the stream. */
      providerRequestsUsed?: number;
      /** Sanitized delay hint only; raw headers and bodies are never retained. */
      retryAfterSeconds?: number;
      telemetry?: AiTurnTelemetry;
    }
  | {
      kind: "generic_error";
      message: string;
      code?: string;
      providerRequestsUsed?: number;
      retryAfterSeconds?: number;
      telemetry?: AiTurnTelemetry;
    }
  | { kind: "no_terminal"; telemetry?: AiTurnTelemetry };

export type ConsumeAIStreamCallbacks = {
  onCandidate: (candidate: AICandidate) => void;
  onDone?: (data: Record<string, unknown>) => void;
  onStatus: (message: string) => void;
  onTelemetry?: (telemetry: AiTurnTelemetry) => void;
};

export function telemetryFromSsePayload(
  json: Record<string, unknown>,
): AiTurnTelemetry | null {
  const completionSource = asAiCompletionSource(json.completion_source);
  const probeStatus =
    typeof json.probe_status === "string" ? json.probe_status : null;
  const repairAttempted =
    typeof json.repair_attempted === "boolean" ? json.repair_attempted : null;
  const terminalCause =
    typeof json.terminal_cause === "string" ? json.terminal_cause : null;
  const thinkingStatus = typeof json.status === "string" ? json.status : null;
  const message = typeof json.message === "string" ? json.message : null;
  const humanState = describeAiTurnTelemetry({
    completionSource,
    probeStatus,
    repairAttempted,
    terminalCause,
    thinkingStatus,
    message,
  });
  if (
    !completionSource &&
    !probeStatus &&
    repairAttempted === null &&
    !terminalCause &&
    !humanState
  ) {
    return null;
  }
  return {
    completionSource,
    probeStatus,
    repairAttempted,
    terminalCause,
    humanState,
  };
}

function isCodedProviderErrorCode(value: string): value is CodedProviderErrorCode {
  return (CODED_PROVIDER_ERROR_CODES as readonly string[]).includes(value);
}

function attachTelemetry<T extends object>(
  terminal: T,
  telemetry: AiTurnTelemetry | null | undefined,
): T {
  if (!telemetry) return terminal;
  return { ...terminal, telemetry };
}

function recordErrorEvent(
  json: Record<string, unknown>,
  lastTelemetry: AiTurnTelemetry | null,
): Exclude<AiMoveStreamTerminal, { kind: "done" } | { kind: "no_terminal" }> {
  const message = typeof json.error === "string" ? json.error : "AI error";
  const code = typeof json.code === "string" ? json.code : undefined;
  const providerRequestsUsed =
    typeof json.provider_requests_used === "number" &&
    Number.isFinite(json.provider_requests_used) &&
    json.provider_requests_used >= 0
      ? Math.floor(json.provider_requests_used)
      : undefined;
  const retryAfterSeconds =
    typeof json.retry_after_seconds === "number" &&
    Number.isFinite(json.retry_after_seconds) &&
    json.retry_after_seconds >= 0 &&
    json.retry_after_seconds <= 86_400
      ? Math.floor(json.retry_after_seconds)
      : undefined;
  const telemetry = telemetryFromSsePayload(json) ?? lastTelemetry;
  if (code && isCodedProviderErrorCode(code)) {
    return attachTelemetry(
      {
        kind: "coded_provider_error" as const,
        code,
        message,
        ...(providerRequestsUsed !== undefined ? { providerRequestsUsed } : {}),
        ...(retryAfterSeconds !== undefined ? { retryAfterSeconds } : {}),
      },
      telemetry,
    );
  }
  return attachTelemetry(
    {
      kind: "generic_error" as const,
      message,
      code,
      ...(providerRequestsUsed !== undefined ? { providerRequestsUsed } : {}),
      ...(retryAfterSeconds !== undefined ? { retryAfterSeconds } : {}),
    },
    telemetry,
  );
}

type StreamParseState = {
  doneData: Record<string, unknown> | null;
  lastError: Exclude<
    AiMoveStreamTerminal,
    { kind: "done" } | { kind: "no_terminal" }
  > | null;
  lastTelemetry: AiTurnTelemetry | null;
};

function applySseEvent(
  json: Record<string, unknown>,
  callbacks: ConsumeAIStreamCallbacks,
  state: StreamParseState,
): void {
  const type = json.type;
  if (type === "candidate") {
    callbacks.onCandidate({
      word: typeof json.word === "string" ? json.word : "???",
      score: typeof json.score === "number" ? json.score : 0,
      valid: typeof json.valid === "boolean" ? json.valid : false,
      isBest: typeof json.isBest === "boolean" ? json.isBest : false,
      timestamp: typeof json.timestamp === "number" ? json.timestamp : 0,
      allWords: Array.isArray(json.allWords)
        ? json.allWords.filter((word): word is string => typeof word === "string")
        : undefined,
    });
    return;
  }
  if (type === "thinking") {
    if (typeof json.message === "string" && json.message.length > 0) {
      callbacks.onStatus(json.message);
    } else if (typeof json.model === "string") {
      callbacks.onStatus(`Thinking with ${json.model}`);
    }
    const telemetry = telemetryFromSsePayload(json);
    if (telemetry) {
      state.lastTelemetry = telemetry;
      callbacks.onTelemetry?.(telemetry);
    }
    return;
  }
  if (type === "tool_use") {
    callbacks.onStatus(
      json.tool === "validateMove"
        ? `Testing ${json.tileCount ?? "new"} tile move...`
        : "Checking candidate words against the dictionary...",
    );
    return;
  }
  if (type === "tool_result") {
    if (json.tool === "validateMove") {
      callbacks.onStatus(
        json.valid
          ? `Valid move found for ${json.score ?? 0} points.`
          : "Rejected. Trying another line...",
      );
    }
    return;
  }
  if (type === "done") {
    state.doneData = json;
    callbacks.onDone?.(json);
    const telemetry = telemetryFromSsePayload(json);
    if (telemetry) {
      state.lastTelemetry = telemetry;
      callbacks.onTelemetry?.(telemetry);
    }
    return;
  }
  if (type === "error") {
    if (state.doneData) return;
    state.lastError = recordErrorEvent(json, state.lastTelemetry);
    const telemetry = telemetryFromSsePayload(json) ?? state.lastTelemetry;
    if (telemetry) {
      state.lastTelemetry = telemetry;
      callbacks.onTelemetry?.(telemetry);
    }
  }
}

function consumeSseBuffer(
  chunk: string,
  callbacks: ConsumeAIStreamCallbacks,
  state: StreamParseState,
): void {
  const trimmed = chunk.trim();
  if (!trimmed.startsWith("data: ")) return;
  try {
    const json = JSON.parse(trimmed.slice(6)) as unknown;
    if (typeof json !== "object" || json === null || Array.isArray(json)) return;
    applySseEvent(json as Record<string, unknown>, callbacks, state);
  } catch {
    /* malformed line — not a terminal */
  }
}

function finishTerminal(state: StreamParseState): AiMoveStreamTerminal {
  if (state.doneData) return { kind: "done", data: state.doneData };
  if (state.lastError) return state.lastError;
  return attachTelemetry({ kind: "no_terminal" as const }, state.lastTelemetry);
}

/**
 * Consume one `/api/ai/move` SSE body and return a single terminal.
 * A `type: done` event always wins over a later disconnect, malformed line,
 * or error event.
 */
export async function consumeAIStream(
  response: Response,
  callbacks: ConsumeAIStreamCallbacks,
): Promise<AiMoveStreamTerminal> {
  const reader = response.body?.getReader();
  if (!reader) {
    return { kind: "generic_error", message: "No response stream" };
  }

  const decoder = new TextDecoder();
  const state: StreamParseState = {
    doneData: null,
    lastError: null,
    lastTelemetry: null,
  };
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        consumeSseBuffer(line, callbacks, state);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) {
      consumeSseBuffer(buffer, callbacks, state);
    }
  } catch (error) {
    if (state.doneData) return { kind: "done", data: state.doneData };
    if (state.lastError) return state.lastError;
    return attachTelemetry(
      {
        kind: "generic_error" as const,
        message: error instanceof Error ? error.message : "AI stream failed",
      },
      state.lastTelemetry,
    );
  }

  return finishTerminal(state);
}
