import { beforeEach, describe, expect, it } from "vitest";
import { useGameStore } from "./useGameStore";

function attempt(modelId: string, extra = {}) {
  return { provider: "openrouter", modelId, status: "pending" as const, ...extra };
}

describe("fallback progress store state", () => {
  beforeEach(() => {
    useGameStore.setState(useGameStore.getInitialState(), true);
  });

  it("stores ordered attempts and resets the active index", () => {
    const queue = [attempt("a"), attempt("b"), attempt("c")];
    useGameStore.getState().setAIFallbackActiveIndex(2);
    useGameStore.getState().setAIFallbackAttempts(queue);

    expect(useGameStore.getState().aiFallbackAttempts).toEqual(queue);
    expect(useGameStore.getState().aiFallbackActiveIndex).toBeNull();
  });

  it("binds the active attempt index", () => {
    useGameStore.getState().setAIFallbackAttempts([attempt("a"), attempt("b")]);
    useGameStore.getState().setAIFallbackActiveIndex(1);

    expect(useGameStore.getState().aiFallbackActiveIndex).toBe(1);
  });

  it("marks only the failed attempt", () => {
    const queue = [attempt("a"), attempt("b"), attempt("c")];
    useGameStore.getState().setAIFallbackAttempts(queue);
    useGameStore.getState().markAIFallbackFailed(1);

    expect(useGameStore.getState().aiFallbackAttempts.map((a) => a.status)).toEqual([
      "pending",
      "failed",
      "pending",
    ]);
  });

  it("clears progress completely", () => {
    useGameStore.getState().setAIFallbackAttempts([attempt("a")]);
    useGameStore.getState().setAIFallbackActiveIndex(0);
    useGameStore.getState().patchAITurnTelemetry({
      humanState: "providers exhausted",
    });
    useGameStore.getState().clearAIFallbackProgress();

    expect(useGameStore.getState().aiFallbackAttempts).toEqual([]);
    expect(useGameStore.getState().aiFallbackActiveIndex).toBeNull();
    expect(useGameStore.getState().aiTurnTelemetry).toBeNull();
  });

  it("resets fallback progress with the game UI", () => {
    useGameStore.getState().setAIFallbackAttempts([attempt("a")]);
    useGameStore.getState().setAIFallbackActiveIndex(0);
    useGameStore.getState().patchAITurnTelemetry({
      completionSource: "genuine_no_move_pass",
      humanState: "genuine dead rack — passing",
    });
    useGameStore.getState().resetGameUi();

    expect(useGameStore.getState().aiFallbackAttempts).toEqual([]);
    expect(useGameStore.getState().aiFallbackActiveIndex).toBeNull();
    expect(useGameStore.getState().aiTurnTelemetry).toBeNull();
  });

  it("keeps turn telemetry out of the persisted slice", () => {
    useGameStore.getState().patchAITurnTelemetry({
      humanState: "backend found a legal rescue; repairing",
    });
    const partialize = useGameStore.persist.getOptions().partialize;
    expect(partialize).toBeTypeOf("function");
    const sliced = partialize!(useGameStore.getState());
    expect(sliced).not.toHaveProperty("aiTurnTelemetry");
    expect(sliced).not.toHaveProperty("aiFallbackAttempts");
    expect(sliced).not.toHaveProperty("aiCandidates");
    expect(sliced).not.toHaveProperty("aiStatusMessage");
  });
});
