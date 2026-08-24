import type { AICandidate } from "./types";

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
    }
  | {
      kind: "generic_error";
      message: string;
      code?: string;
    }
  | { kind: "no_terminal" };

export type ConsumeAIStreamCallbacks = {
  onCandidate: (candidate: AICandidate) => void;
  onDone?: (data: Record<string, unknown>) => void;
  onStatus: (message: string) => void;
};

function isCodedProviderErrorCode(value: string): value is CodedProviderErrorCode {
  return (CODED_PROVIDER_ERROR_CODES as readonly string[]).includes(value);
}

function recordErrorEvent(
  json: Record<string, unknown>,
): Exclude<AiMoveStreamTerminal, { kind: "done" } | { kind: "no_terminal" }> {
  const message = typeof json.error === "string" ? json.error : "AI error";
  const code = typeof json.code === "string" ? json.code : undefined;
  if (code && isCodedProviderErrorCode(code)) {
    return { kind: "coded_provider_error", code, message };
  }
  return { kind: "generic_error", message, code };
}

function applySseEvent(
  json: Record<string, unknown>,
  callbacks: ConsumeAIStreamCallbacks,
  state: {
    doneData: Record<string, unknown> | null;
    lastError: Exclude<
      AiMoveStreamTerminal,
      { kind: "done" } | { kind: "no_terminal" }
    > | null;
  },
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
    return;
  }
  if (type === "error") {
    if (state.doneData) return;
    state.lastError = recordErrorEvent(json);
  }
}

function consumeSseBuffer(
  chunk: string,
  callbacks: ConsumeAIStreamCallbacks,
  state: {
    doneData: Record<string, unknown> | null;
    lastError: Exclude<
      AiMoveStreamTerminal,
      { kind: "done" } | { kind: "no_terminal" }
    > | null;
  },
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

function finishTerminal(state: {
  doneData: Record<string, unknown> | null;
  lastError: Exclude<
    AiMoveStreamTerminal,
    { kind: "done" } | { kind: "no_terminal" }
  > | null;
}): AiMoveStreamTerminal {
  if (state.doneData) return { kind: "done", data: state.doneData };
  if (state.lastError) return state.lastError;
  return { kind: "no_terminal" };
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
  const state: {
    doneData: Record<string, unknown> | null;
    lastError: Exclude<
      AiMoveStreamTerminal,
      { kind: "done" } | { kind: "no_terminal" }
    > | null;
  } = { doneData: null, lastError: null };
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
    return {
      kind: "generic_error",
      message: error instanceof Error ? error.message : "AI stream failed",
    };
  }

  return finishTerminal(state);
}
