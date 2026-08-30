import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const motionMock = vi.hoisted(() => ({ reduced: false }));

vi.mock("framer-motion", async (importOriginal) => {
  const actual = await importOriginal<typeof import("framer-motion")>();
  return {
    ...actual,
    useReducedMotion: () => motionMock.reduced,
  };
});

import { AIThinkingOverlay } from "./AIThinkingOverlay";
import { useGameStore } from "@/hooks/useGameStore";

const GEMMA = "google/gemma-4-31b-it:free";
const GLM = "z-ai/glm-5.2:free";
const NIM = "nvidia/nemotron-3-super-120b-a12b";

type Attempt = { provider: string; modelId: string; status: "pending" | "active" | "failed" };

/**
 * Node SSR reads zustand's server snapshot (getInitialState). Priming that
 * snapshot exercises the exact store-driven render path used in the browser
 * once the live store has been updated during a turn.
 */
function primeStore(attempts: Attempt[], activeIndex: number | null, extra = {}) {
  Object.assign(useGameStore.getInitialState(), {
    aiThinking: true,
    aiCandidates: [],
    aiStatusMessage: null,
    aiCountdown: 30,
    aiFallbackAttempts: attempts,
    aiFallbackActiveIndex: activeIndex,
    ...extra,
  });
}

function pending(modelId: string): Attempt {
  return { provider: "openrouter", modelId, status: "pending" };
}

function renderOverlay() {
  return renderToStaticMarkup(createElement(AIThinkingOverlay));
}

beforeEach(() => {
  motionMock.reduced = false;
  primeStore([], null, { premiumLookEnabled: true });
});

afterEach(() => {
  primeStore([], null, { premiumLookEnabled: true });
});

describe("AIThinkingOverlay fallback attempt pills", () => {
  it("renders no progress strip when the store has no attempts", () => {
    expect(renderOverlay()).not.toContain("ai-fallback-progress");
  });

  it("renders ordered pills straight from store state", () => {
    primeStore(
      [
        pending(GEMMA),
        { provider: "openrouter", modelId: GLM, status: "failed" },
        { provider: "nvidia-nim", modelId: NIM, status: "pending" },
      ],
      null,
    );
    const markup = renderOverlay();
    expect(markup).toContain("ai-fallback-progress");
    expect(markup.indexOf(GEMMA)).toBeGreaterThan(-1);
    expect(markup.indexOf(GEMMA)).toBeLessThan(markup.indexOf(GLM));
    expect(markup.indexOf(GLM)).toBeLessThan(markup.indexOf(NIM));
    expect(markup).toContain('data-attempt-status="failed"');
    expect(markup).toContain('data-attempt-status="pending"');
  });

  it("renders five direct-provider pills in exact order with one active tile", () => {
    const attempts: Attempt[] = [
      { provider: "groq", modelId: "openai/gpt-oss-120b", status: "failed" },
      { provider: "google-gemini", modelId: "gemini-3.7-flash", status: "pending" },
      {
        provider: "cloudflare-workers-ai",
        modelId: "@cf/zai-org/glm-4.7-flash",
        status: "pending",
      },
      { provider: "mistral", modelId: "mistral-small-2603", status: "pending" },
      {
        provider: "ibm-watsonx",
        modelId: "ibm/granite-4-h-small",
        status: "pending",
      },
    ];
    primeStore(attempts, 2);
    const markup = renderOverlay();
    const labels = [
      "Groq",
      "Google Gemini",
      "Cloudflare Workers AI",
      "Mistral",
      "IBM watsonx.ai",
    ];
    for (let index = 0; index < labels.length; index += 1) {
      expect(markup).toContain(labels[index]);
      if (index > 0) {
        expect(markup.indexOf(labels[index - 1])).toBeLessThan(
          markup.indexOf(labels[index]),
        );
      }
    }
    expect(markup.match(/data-attempt-status=/g)?.length).toBe(5);
    expect(markup.match(/data-pingpong="active"/g)?.length).toBe(1);
  });

  it("binds exactly one ping-pong tile to the active attempt lifecycle", () => {
    primeStore([pending(GEMMA), pending(GLM)], 1);
    const markup = renderOverlay();
    expect(markup.match(/data-pingpong="active"/g)?.length).toBe(1);
    expect(markup).toContain('data-attempt-status="active"');
    // The animated tile belongs to the second pill only.
    expect(markup.indexOf('data-pingpong="active"')).toBeGreaterThan(
      markup.indexOf(GLM),
    );
  });

  it("shows no ping-pong when no attempt is active or the active one failed", () => {
    primeStore([{ provider: "openrouter", modelId: GEMMA, status: "failed" }], 0);
    let markup = renderOverlay();
    expect(markup).not.toContain('data-pingpong="active"');
    expect(markup).not.toContain('data-pingpong="static"');
    expect(markup).toContain('data-attempt-status="failed"');

    primeStore([pending(GEMMA)], null);
    markup = renderOverlay();
    expect(markup).not.toContain('data-pingpong="active"');
  });

  it("renders a static tile under reduced motion", () => {
    motionMock.reduced = true;
    primeStore([pending(GEMMA)], 0);
    const markup = renderOverlay();
    expect(markup).toContain('data-pingpong="static"');
    expect(markup).not.toContain('data-pingpong="active"');
    expect(markup).toContain('data-attempt-status="active"');
  });

  it("stays readable with Premium Look disabled (flat amber tile, same data)", () => {
    primeStore([{ provider: "nvidia-nim", modelId: NIM, status: "pending" }], 0, {
      premiumLookEnabled: false,
    });
    const markup = renderOverlay();
    expect(markup).toContain(NIM);
    expect(markup).toContain("bg-amber-400");
    expect(markup).toContain('data-pingpong="active"');
    expect(markup).not.toMatch(/linear-gradient\(135deg/); // no gold/black chrome
  });

  it("applies gold/black chrome when Premium Look is enabled", () => {
    primeStore([pending(NIM)], 0, { premiumLookEnabled: true });
    const markup = renderOverlay();
    expect(markup).toMatch(/linear-gradient\(135deg/);
    expect(markup).toContain('data-pingpong="active"');
  });

  it("renders transient telemetry inside the attempt-progress surface", () => {
    primeStore([pending(GEMMA)], 0, {
      aiTurnTelemetry: {
        probeStatus: "found",
        repairAttempted: true,
        humanState: "backend found a legal rescue; repairing",
      },
    });
    const markup = renderOverlay();
    expect(markup).toContain("ai-turn-telemetry");
    expect(markup).toContain("backend found a legal rescue; repairing");
    expect(markup).toContain("ai-fallback-progress");
    expect(markup.indexOf(GEMMA)).toBeGreaterThan(-1);
  });

  it("renders genuine-dead and exhausted states without touching ping-pong", () => {
    primeStore(
      [
        { provider: "openrouter", modelId: GEMMA, status: "failed" },
        pending(GLM),
      ],
      1,
      {
        aiTurnTelemetry: { humanState: "genuine dead rack — exchanging" },
      },
    );
    let markup = renderOverlay();
    expect(markup).toContain("genuine dead rack — exchanging");
    expect(markup.match(/data-pingpong="active"/g)?.length).toBe(1);

    primeStore([{ provider: "openrouter", modelId: GEMMA, status: "failed" }], 0, {
      aiTurnTelemetry: { humanState: "providers exhausted" },
    });
    markup = renderOverlay();
    expect(markup).toContain("providers exhausted");
    expect(markup).not.toContain('data-pingpong="active"');
    expect(markup).not.toContain('data-pingpong="static"');
  });

  it("keeps reduced-motion static tile when telemetry is present", () => {
    motionMock.reduced = true;
    primeStore([pending(GEMMA)], 0, {
      aiTurnTelemetry: {
        humanState: "backend found a legal rescue; repairing",
      },
    });
    const markup = renderOverlay();
    expect(markup).toContain("backend found a legal rescue; repairing");
    expect(markup).toContain('data-pingpong="static"');
    expect(markup).not.toContain('data-pingpong="active"');
    expect(markup).toContain('data-attempt-status="active"');
  });

  it("renders backend rescue failure telemetry inside attempt progress", () => {
    primeStore([pending(GEMMA)], 0, {
      aiTurnTelemetry: {
        terminalCause: "backend_rescue_error",
        humanState: "backend rescue failed",
      },
    });
    const markup = renderOverlay();
    expect(markup).toContain("ai-turn-telemetry");
    expect(markup).toContain("backend rescue failed");
    expect(markup).toContain("ai-fallback-progress");
    expect(markup.match(/data-pingpong="active"/g)?.length).toBe(1);
  });
});
