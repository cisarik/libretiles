import { describe, expect, it } from "vitest";
import { consumeAIStream, type AiMoveStreamTerminal } from "./ai-move-stream";
import type { AICandidate, AiTurnTelemetry } from "./types";

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let index = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index]));
        index += 1;
        return;
      }
      controller.close();
    },
  });
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream" },
  });
}

function eventLine(payload: Record<string, unknown>): string {
  return `data: ${JSON.stringify(payload)}\n`;
}

async function collect(
  response: Response,
): Promise<{
  terminal: AiMoveStreamTerminal;
  candidates: AICandidate[];
  statuses: string[];
  doneCallbacks: Record<string, unknown>[];
}> {
  const candidates: AICandidate[] = [];
  const statuses: string[] = [];
  const doneCallbacks: Record<string, unknown>[] = [];
  const terminal = await consumeAIStream(response, {
    onCandidate: (candidate) => {
      candidates.push(candidate);
    },
    onStatus: (message) => {
      statuses.push(message);
    },
    onDone: (data) => {
      doneCallbacks.push(data);
    },
  });
  return { terminal, candidates, statuses, doneCallbacks };
}

describe("consumeAIStream terminals", () => {
  it("returns done and keeps overlay callbacks", async () => {
    const { terminal, candidates, statuses, doneCallbacks } = await collect(
      sseResponse([
        eventLine({ type: "thinking", message: "Opening book" }),
        eventLine({
          type: "tool_use",
          tool: "validateMove",
          tileCount: 7,
        }),
        eventLine({
          type: "candidate",
          word: "QI",
          score: 11,
          valid: true,
          isBest: true,
          timestamp: 1,
        }),
        eventLine({ type: "done", ok: true, action: "place" }),
      ]),
    );

    expect(terminal).toEqual({
      kind: "done",
      data: { type: "done", ok: true, action: "place" },
    });
    expect(doneCallbacks).toHaveLength(1);
    expect(candidates[0]?.word).toBe("QI");
    expect(statuses).toContain("Opening book");
    expect(statuses).toContain("Testing 7 tile move...");
  });

  it("returns coded provider_auth_failed", async () => {
    const { terminal } = await collect(
      sseResponse([
        eventLine({
          type: "error",
          code: "provider_auth_failed",
          error: "This free rival could not authenticate.",
        }),
      ]),
    );
    expect(terminal.kind).toBe("coded_provider_error");
    if (terminal.kind === "coded_provider_error") {
      expect(terminal.code).toBe("provider_auth_failed");
      expect(terminal).not.toHaveProperty("creditBalance");
    }
  });

  it("does not carry legacy credit fields into an error terminal", async () => {
    const { terminal } = await collect(
      sseResponse([
        eventLine({
          type: "error",
          code: "backend_failed",
          error: "Django rejected the move",
          credit_balance: "12.34",
        }),
      ]),
    );
    expect(terminal).toEqual({
      kind: "generic_error",
      code: "backend_failed",
      message: "Django rejected the move",
    });
  });

  it("returns coded provider_rate_limited from a nested-style SSE error", async () => {
    const { terminal } = await collect(
      sseResponse([
        eventLine({
          type: "error",
          code: "provider_rate_limited",
          error: "This free rival is rate limited.",
        }),
      ]),
    );
    expect(terminal.kind).toBe("coded_provider_error");
    if (terminal.kind === "coded_provider_error") {
      expect(terminal.code).toBe("provider_rate_limited");
    }
  });

  it("accepts only finite numeric retry-after values in 0..86400", async () => {
    for (const retryAfterSeconds of [0, 86_400]) {
      const { terminal } = await collect(
        sseResponse([
          eventLine({
            type: "error",
            code: "provider_rate_limited",
            error: "rate limited",
            retry_after_seconds: retryAfterSeconds,
            raw_headers: { authorization: "Bearer should-not-survive" },
            response_body: "sk-live-should-not-survive",
          }),
        ]),
      );
      expect(terminal).toEqual({
        kind: "coded_provider_error",
        code: "provider_rate_limited",
        message: "rate limited",
        retryAfterSeconds,
      });
      expect(JSON.stringify(terminal)).not.toMatch(/Bearer |sk-live|raw_headers|response_body/);
    }

    for (const retryAfterSeconds of [-1, 86_401, "12", null]) {
      const { terminal } = await collect(
        sseResponse([
          eventLine({
            type: "error",
            code: "provider_rate_limited",
            error: "rate limited",
            retry_after_seconds: retryAfterSeconds,
          }),
        ]),
      );
      expect(terminal).not.toHaveProperty("retryAfterSeconds");
    }
  });

  it("rejects NaN and infinite retry-after values before they reach terminals", async () => {
    for (const token of ["NaN", "Infinity", "-Infinity"]) {
      const line =
        `data: {"type":"error","code":"provider_rate_limited",` +
        `"error":"rate limited","retry_after_seconds":${token}}\n`;
      const { terminal } = await collect(sseResponse([line]));
      expect(terminal).toEqual({ kind: "no_terminal" });
    }
  });

  it("returns coded provider_unavailable", async () => {
    const { terminal } = await collect(
      sseResponse([
        eventLine({
          type: "error",
          code: "provider_unavailable",
          error: "This free rival is temporarily unavailable.",
        }),
      ]),
    );
    expect(terminal.kind).toBe("coded_provider_error");
    if (terminal.kind === "coded_provider_error") {
      expect(terminal.code).toBe("provider_unavailable");
    }
  });

  it("treats unknown error codes as generic_error", async () => {
    const { terminal } = await collect(
      sseResponse([
        eventLine({
          type: "error",
          code: "backend_failed",
          error: "Django rejected the move",
        }),
      ]),
    );
    expect(terminal).toMatchObject({
      kind: "generic_error",
      code: "backend_failed",
    });
  });

  it("does not create a terminal from malformed events", async () => {
    const { terminal, candidates } = await collect(
      sseResponse([
        "data: {not-json\n",
        eventLine({ type: "candidate", word: "OK", score: 8, valid: true }),
        "not-sse-at-all\n",
      ]),
    );
    expect(terminal).toEqual({ kind: "no_terminal" });
    expect(candidates).toHaveLength(1);
  });

  it("lets done win over a later error event", async () => {
    const { terminal } = await collect(
      sseResponse([
        eventLine({ type: "done", ok: true, action: "pass" }),
        eventLine({
          type: "error",
          code: "provider_rate_limited",
          error: "late error",
        }),
      ]),
    );
    expect(terminal.kind).toBe("done");
    if (terminal.kind === "done") {
      expect(terminal.data.action).toBe("pass");
    }
  });

  it("lets done win over a disconnect after the done event", async () => {
    const { terminal } = await collect(
      sseResponse([
        eventLine({ type: "done", ok: true, action: "exchange" }),
        "data: {truncated",
      ]),
    );
    expect(terminal).toEqual({
      kind: "done",
      data: { type: "done", ok: true, action: "exchange" },
    });
  });

  it("returns generic_error when the body is missing", async () => {
    const terminal = await consumeAIStream(
      { body: null } as Response,
      {
        onCandidate: () => {},
        onStatus: () => {},
      },
    );
    expect(terminal).toEqual({
      kind: "generic_error",
      message: "No response stream",
    });
  });

  it("forwards terminal telemetry without persisting private payloads", async () => {
    const events: AiTurnTelemetry[] = [];
    const terminal = await consumeAIStream(
      sseResponse([
        eventLine({
          type: "thinking",
          status: "genuine_exchange",
          message: "genuine dead rack — exchanging",
          probe_status: "none",
        }),
        eventLine({
          type: "done",
          ok: true,
          action: "exchange",
          completion_source: "genuine_no_move_exchange",
          probe_status: "none",
          repair_attempted: false,
          terminal_cause: "genuine_no_move_exchange",
        }),
      ]),
      {
        onCandidate: () => {},
        onStatus: () => {},
        onTelemetry: (item) => {
          events.push(item);
        },
      },
    );
    expect(terminal.kind).toBe("done");
    expect(events.map((item) => item.humanState)).toEqual([
      "genuine dead rack — exchanging",
      "genuine dead rack — exchanging",
    ]);
    expect(events[1]).toMatchObject({
      completionSource: "genuine_no_move_exchange",
      probeStatus: "none",
      repairAttempted: false,
      terminalCause: "genuine_no_move_exchange",
    });
    expect(JSON.stringify(events)).not.toMatch(/sk-live|Bearer |api[_-]?key/i);
  });
});
