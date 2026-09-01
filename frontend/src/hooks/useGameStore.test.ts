import { beforeEach, describe, expect, it } from "vitest";
import { adoptBrowserLocaleIfUnset, useGameStore } from "./useGameStore";

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

  it("uses 120 seconds and 50 steps for a fresh store", () => {
    expect(useGameStore.getState().aiTimeout).toBe(120);
    expect(useGameStore.getState().aiMaxSteps).toBe(50);
  });

  it("preserves persisted legacy and custom AI budgets unchanged", async () => {
    const migrate = useGameStore.persist.getOptions().migrate;
    expect(migrate).toBeTypeOf("function");
    for (const saved of [
      { aiTimeout: 30, aiMaxSteps: 30 },
      { aiTimeout: 180, aiMaxSteps: 80 },
    ]) {
      const migrated = (await migrate!(saved, 1)) as typeof saved;
      expect(migrated.aiTimeout).toBe(saved.aiTimeout);
      expect(migrated.aiMaxSteps).toBe(saved.aiMaxSteps);
    }
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
    expect(sliced).toHaveProperty("selectedVariantSlug");
  });
});

describe("persist migrate to version 2", () => {
  it("defaults a v1 persist without a slug to english and keeps budgets", async () => {
    const migrate = useGameStore.persist.getOptions().migrate;
    expect(migrate).toBeTypeOf("function");
    const migrated = (await migrate!(
      { aiTimeout: 30, aiMaxSteps: 30 },
      1,
    )) as Record<string, unknown>;
    expect(migrated.selectedVariantSlug).toBe("english");
    expect(migrated.aiTimeout).toBe(30);
    expect(migrated.aiMaxSteps).toBe(30);
    expect(migrated).not.toHaveProperty("localAIContextLength");
    expect(migrated).not.toHaveProperty("localAIReloadAfterTurn");
  });

  it("keeps an explicit slovak slug already present on a v1 persist", async () => {
    const migrate = useGameStore.persist.getOptions().migrate;
    expect(migrate).toBeTypeOf("function");
    const migrated = (await migrate!(
      { selectedVariantSlug: "slovak", aiTimeout: 180, aiMaxSteps: 80 },
      1,
    )) as Record<string, unknown>;
    expect(migrated.selectedVariantSlug).toBe("slovak");
    expect(migrated.aiTimeout).toBe(180);
    expect(migrated.aiMaxSteps).toBe(80);
  });

  it("rewrites a garbage slug to english", async () => {
    const migrate = useGameStore.persist.getOptions().migrate;
    expect(migrate).toBeTypeOf("function");
    const migrated = (await migrate!(
      { selectedVariantSlug: "french", aiTimeout: 60, aiMaxSteps: 20 },
      1,
    )) as Record<string, unknown>;
    expect(migrated.selectedVariantSlug).toBe("english");
    expect(migrated.aiTimeout).toBe(60);
    expect(migrated.aiMaxSteps).toBe(20);
  });
});

describe("AC-ONCE explicit locale is sticky", () => {
  beforeEach(() => {
    useGameStore.setState(useGameStore.getInitialState(), true);
  });

  it("does not replace a stored English locale with a Slovak browser", () => {
    useGameStore.getState().setUiLocale("en");
    expect(adoptBrowserLocaleIfUnset(["sk-SK", "sk"])).toBe("en");
    expect(useGameStore.getState().uiLocale).toBe("en");
  });
});

describe("AC-MIGRATE persist version 2 to 3", () => {
  it("yields uiLocale null when a v2 payload has no locale", async () => {
    expect(useGameStore.persist.getOptions().version).toBe(3);
    const migrate = useGameStore.persist.getOptions().migrate;
    expect(migrate).toBeTypeOf("function");
    const migrated = (await migrate!(
      { selectedVariantSlug: "english", aiTimeout: 30 },
      2,
    )) as Record<string, unknown>;
    expect(migrated.uiLocale).toBeNull();
    expect(migrated.selectedVariantSlug).toBe("english");
  });

  it("rewrites a garbage uiLocale to null and preserves a valid stored value", async () => {
    expect(useGameStore.persist.getOptions().version).toBe(3);
    const migrate = useGameStore.persist.getOptions().migrate;
    expect(migrate).toBeTypeOf("function");
    const garbage = (await migrate!(
      { selectedVariantSlug: "english", uiLocale: "fr" },
      2,
    )) as Record<string, unknown>;
    expect(garbage.uiLocale).toBeNull();
    const migrated = (await migrate!(
      { selectedVariantSlug: "slovak", uiLocale: "sk" },
      2,
    )) as Record<string, unknown>;
    expect(migrated.uiLocale).toBe("sk");
  });
});
