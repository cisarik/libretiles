import { describe, expect, it } from "vitest";
import { createInspectionTraceCollector, sanitizeInspectionTrace } from "./ai-inspection-trace";

describe("AI inspection trace", () => {
  it("records rejected validation, repair, and finish events without raw fields", () => {
    let now = 100;
    const collector = createInspectionTraceCollector({ attemptIndex: 0, startedAt: 0, now: () => now });
    const complete = collector.beginValidate([{ row: 7, col: 7, letter: "A", prompt: "secret" }]);
    now = 120;
    complete({ valid: false, words: [{ word: "AA", valid: false }], reason_code: "invalid_word", raw: "secret" });
    collector.startRepair();
    collector.finishMove();
    const trace = collector.snapshot({ provider: "openrouter", modelId: "model/free", outcome: "done", providerRequestsUsed: 2 });
    expect(trace.attempts[0].events).toEqual([
      expect.objectContaining({ tool: "validateMove", valid: false, words: ["AA"], rejection_code: "invalid_word" }),
      expect.objectContaining({ tool: "phase", marker: "repair_start" }),
      expect.objectContaining({ tool: "finishMove", ready: true }),
    ]);
    expect(JSON.stringify(trace)).not.toContain("secret");
  });

  it("caps every attempt at 64 events and the turn at three attempts", () => {
    const collector = createInspectionTraceCollector({ attemptIndex: 2, previous: { version: 1, attempts: [0, 1].map((attempt_index) => ({ attempt_index, events: [] })) } });
    for (let index = 0; index < 70; index += 1) collector.finishMove();
    const trace = collector.snapshot({ outcome: "error" });
    expect(trace.attempts).toHaveLength(3);
    expect(trace.attempts[2].events).toHaveLength(64);
    expect(trace.attempts[2].truncated).toBe(true);
  });

  it("rejects malformed envelopes", () => {
    expect(sanitizeInspectionTrace({ version: 2, attempts: [] })).toBeNull();
    expect(sanitizeInspectionTrace({ version: 1, attempts: "bad" })).toBeNull();
  });
});
