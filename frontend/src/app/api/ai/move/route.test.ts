import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { generateTextMock, getLanguageModelMock } = vi.hoisted(() => ({
  generateTextMock: vi.fn(),
  getLanguageModelMock: vi.fn(() => ({ provider: "test", modelId: "test" })),
}));

vi.mock("ai", () => ({
  generateText: generateTextMock,
  stepCountIs: vi.fn(() => "stop-condition"),
  tool: vi.fn((definition) => definition),
}));

vi.mock("@/lib/ai-runtimes", () => ({
  findCuratedPair: vi.fn(() => ({
    provider: "openrouter",
    modelId: "google/gemma-4-31b-it:free",
  })),
  getLanguageModel: getLanguageModelMock,
  isLegalBackendTerminal: (value: unknown) =>
    typeof value === "object" && value !== null && "ok" in value && value.ok === true,
  normalizeProviderError: vi.fn(() => null),
  parseCatalogModelRows: (value: unknown) => value,
  revalidateRuntimePair: vi.fn(() => true),
}));

import { POST } from "./route";

const MODEL_ID = "google/gemma-4-31b-it:free";

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function parseSse(text: string): Array<Record<string, unknown>> {
  return text
    .split("\n")
    .filter((line) => line.startsWith("data: "))
    .map((line) => JSON.parse(line.slice(6)) as Record<string, unknown>);
}

function request(): NextRequest {
  return new NextRequest("http://localhost/api/ai/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      game_id: "game-1",
      token: "test-token",
      model_id: MODEL_ID,
      runtime_model_id: MODEL_ID,
      timeout: 30,
      max_steps: 10,
    }),
  });
}

function mockBackend(actionPath: string, actionResult: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/api/catalog/models/")) {
      return jsonResponse([{ provider: "openrouter", model_id: MODEL_ID }]);
    }
    if (url.endsWith("/api/game/game-1/ai-context/")) {
      return jsonResponse({
        compact_state: "empty board",
        ai_state: { ai_rack: "ABCDEFG", human_score: 0, ai_score: 0 },
        is_first_move: true,
        ai_model_id: MODEL_ID,
        ai_move_max_output_tokens: 2000,
      });
    }
    if (url.endsWith(actionPath)) return jsonResponse(actionResult);
    throw new Error(`Unexpected backend request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function runRoute() {
  const response = await POST(request());
  expect(response.headers.get("content-type")).toContain("text/event-stream");
  const events = parseSse(await response.text());
  const done = events.find((event) => event.type === "done");
  expect(done).toBeDefined();
  expect(JSON.stringify(done)).not.toMatch(
    /charge-ai-turn|credit_balance|creditBalance|charged_|billing/i,
  );
  return done;
}

describe("POST /api/ai/move", () => {
  beforeEach(() => {
    generateTextMock.mockReset();
    getLanguageModelMock.mockClear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("applies a place without a billing request or monetary done fields", async () => {
    generateTextMock.mockResolvedValue({
      text: JSON.stringify({
        action: "place",
        placements: [{ row: 7, col: 7, letter: "A" }],
      }),
      steps: [],
    });
    const fetchMock = mockBackend("/api/game/game-1/ai-move/", {
      ok: true,
      action: "place",
      points: 2,
      words: [{ word: "A", score: 2 }],
    });

    expect((await runRoute())?.action).toBe("place");
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/billing/charge-ai-turn/"),
      expect.anything(),
    );
  });

  it("applies a pass without a billing request or monetary done fields", async () => {
    generateTextMock.mockResolvedValue({
      text: JSON.stringify({ action: "pass" }),
      steps: [],
    });
    const fetchMock = mockBackend("/api/game/game-1/ai-pass/", {
      ok: true,
      action: "pass",
    });

    expect((await runRoute())?.action).toBe("pass");
    expect(fetchMock.mock.calls.map(([url]) => String(url))).not.toContain(
      "http://localhost:8000/api/billing/charge-ai-turn/",
    );
  });

  it("applies an exchange without a billing request or monetary done fields", async () => {
    generateTextMock.mockResolvedValue({
      text: JSON.stringify({
        action: "exchange",
        exchange_letters: ["A", "B"],
      }),
      steps: [],
    });
    const fetchMock = mockBackend("/api/game/game-1/ai-exchange/", {
      ok: true,
      action: "exchange",
    });

    expect((await runRoute())?.action).toBe("exchange");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("billing"))).toBe(false);
  });
});
