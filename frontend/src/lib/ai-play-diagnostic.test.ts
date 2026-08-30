import { describe, expect, it } from "vitest";
import {
  COMPLETION_SOURCES,
  buildDiagnosticQueue,
  liveOptInEnabled,
  serializeTerminalObservation,
} from "./ai-play-diagnostic";
import type { AiMoveStreamTerminal } from "./ai-move-stream";

const NIM = {
  provider: "nvidia-nim",
  model_id: "nvidia/nemotron-3-super-120b-a12b",
};
const GEMMA = {
  provider: "openrouter",
  model_id: "google/gemma-4-31b-it:free",
};
const GLM = {
  provider: "openrouter",
  model_id: "z-ai/glm-5.2:free",
};
const CATALOG = [
  GEMMA,
  NIM,
  { provider: "openrouter", model_id: "nvidia/nemotron-3-super-120b-a12b:free" },
  GLM,
  { provider: "openrouter", model_id: "google/gemma-4-26b-a4b-it:free" },
];

describe("ai-play-diagnostic helpers", () => {
  it("keeps selected-only queues at the exact requested pair", () => {
    const queue = buildDiagnosticQueue({
      provider: NIM.provider,
      modelId: NIM.model_id,
      queueMode: "selected-only",
      catalog: CATALOG,
    });
    expect(queue).toEqual([NIM]);
  });

  it("builds a preference-first catalog-fallback queue of at most three pairs", () => {
    const queue = buildDiagnosticQueue({
      provider: NIM.provider,
      modelId: NIM.model_id,
      queueMode: "catalog-fallback",
      catalog: CATALOG,
    });
    expect(queue[0]).toEqual(NIM);
    expect(queue.length).toBeLessThanOrEqual(3);
    expect(queue.length).toBeGreaterThanOrEqual(1);
    const keys = queue.map((row) => `${row.provider}\0${row.model_id}`);
    expect(new Set(keys).size).toBe(queue.length);
  });

  it("serializes the six completion sources and drops headers and bodies", () => {
    for (const source of COMPLETION_SOURCES) {
      const terminal: AiMoveStreamTerminal = {
        kind: "done",
        data: {
          type: "done",
          action: "place",
          completion_source: source,
          words: [{ word: "SČÍTALO", score: 82 }],
          points: 82,
          Authorization: "Bearer secret-token",
          token: "should-drop",
          prompt: "SEARCH PROFILE",
        },
      };
      const observation = serializeTerminalObservation({
        terminal,
        attempts: [
          {
            provider: NIM.provider,
            model_id: NIM.model_id,
            timeout_seconds: 60,
            step_grant: 30,
            provider_requests_used: 0,
          },
        ],
        queue: [NIM],
        turnProviderRequestsUsed: 0,
        lostTerminal: false,
        externalProviderInvocations: 0,
        backendOrigins: ["http://127.0.0.1:9"],
        foreignOrigins: [],
      });
      expect(observation.completion_source).toBe(source);
      expect(JSON.stringify(observation)).not.toContain("Bearer");
      expect(JSON.stringify(observation)).not.toContain("secret-token");
      expect(JSON.stringify(observation)).not.toContain("SEARCH PROFILE");
      expect(observation.formed_words).toEqual(["SČÍTALO"]);
    }
  });

  it("treats live mode as refused without the sentinel", () => {
    expect(liveOptInEnabled({} as NodeJS.ProcessEnv)).toBe(false);
    expect(liveOptInEnabled({ LIBRETILES_AI_PLAY_LIVE: "1" })).toBe(true);
  });
});
