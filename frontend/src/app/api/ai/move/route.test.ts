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
  getLanguageModel: getLanguageModelMock,
  isLegalBackendTerminal: (value: unknown) =>
    typeof value === "object" && value !== null && "ok" in value && value.ok === true,
  normalizeProviderError: vi.fn(() => null),
  parseCatalogModelRows: (value: unknown) => value,
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

function request(overrides: Record<string, unknown> = {}): NextRequest {
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
      ...overrides,
    }),
  });
}

function mockBackend(actionPath: string, actionResult: Record<string, unknown>, catalog = [{ provider: "openrouter", model_id: MODEL_ID }]) {
  const fetchMock = vi.fn(
    async (input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/api/catalog/models/")) {
      return jsonResponse(catalog);
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
    }
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function runRoute(req: NextRequest = request()) {
  const response = await POST(req);
  expect(response.headers.get("content-type")).toContain("text/event-stream");
  const events = parseSse(await response.text());
  const done = events.find((event) => event.type === "done");
  expect(done).toBeDefined();
  expect(JSON.stringify(done)).not.toMatch(
    /charge-ai-turn|credit_balance|creditBalance|charged_|billing/i,
  );
  return { done, events };
}

describe("POST /api/ai/move", () => {
  beforeEach(() => {
    generateTextMock.mockReset();
    generateTextMock.mockResolvedValue({
      text: JSON.stringify({
        action: "place",
        placements: [{ row: 7, col: 7, letter: "A" }],
      }),
      steps: [],
    });
    getLanguageModelMock.mockClear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("applies a place without a billing request or monetary done fields", async () => {
    const fetchMock = mockBackend("/api/game/game-1/ai-move/", {
      ok: true,
      action: "place",
      points: 2,
      words: [{ word: "A", score: 2 }],
    });

    const { done } = await runRoute();
    expect(done?.action).toBe("place");
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

    const { done } = await runRoute();
    expect(done?.action).toBe("pass");
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

    const { done } = await runRoute();
    expect(done?.action).toBe("exchange");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("billing"))).toBe(false);
  });

  it("disables AI SDK retries on the provider stream", async () => {
    mockBackend("/api/game/game-1/ai-move/", {
      ok: true,
      action: "place",
      points: 2,
      words: [{ word: "A", score: 2 }],
    });
    await runRoute();
    expect(generateTextMock).toHaveBeenCalledWith(
      expect.objectContaining({ maxRetries: 0 }),
    );
  });

  it("reports provider_requests_used in terminal metadata", async () => {
    generateTextMock.mockImplementation(async () => ({
      text: JSON.stringify({
        action: "place",
        placements: [{ row: 7, col: 7, letter: "A" }],
      }),
      steps: [
        {
          stepNumber: 1,
          toolCalls: [],
          model: { provider: "openrouter", modelId: MODEL_ID },
          response: { modelId: MODEL_ID },
        },
        {
          stepNumber: 2,
          toolCalls: [],
          model: { provider: "openrouter", modelId: MODEL_ID },
          response: { modelId: MODEL_ID },
        },
      ],
    }));
    mockBackend("/api/game/game-1/ai-move/", {
      ok: true,
      action: "place",
      points: 2,
      words: [{ word: "A", score: 2 }],
    });

    const { done } = await runRoute();
    expect(done?.provider_requests_used).toBe(2);
  });

  it("repairs a stale requested model onto catalog row 1 without PATCHing", async () => {
    // Preference is paid/unknown; catalog row 1 is the only playable pair.
    const fetchMock = mockBackend(
      "/api/game/game-1/ai-move/",
      { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      [{ provider: "openrouter", model_id: MODEL_ID }],
    );

    const { done } = await runRoute(
      request({ model_id: "openai/gpt-5-mini", runtime_model_id: "openai/gpt-5-mini" }),
    );
    expect(done?.action).toBe("place");
    expect(done?.runtime_model).toBe(MODEL_ID);
    const calls = fetchMock.mock.calls as Array<
      [string | URL | Request, RequestInit?]
    >;
    expect(
      calls.some(([, init]) => init?.method === "PATCH"),
    ).toBe(false);
  });

  it("fails closed when the catalog fetch fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/api/catalog/models/")) {
          return new Response("backend down", { status: 503 });
        }
        throw new Error(`Unexpected backend request: ${url}`);
      }),
    );

    const response = await POST(request());
    const events = parseSse(await response.text());
    expect(events.some((event) => event.type === "error")).toBe(true);
    expect(events.some((event) => event.type === "done")).toBe(false);
    expect(getLanguageModelMock).not.toHaveBeenCalled();
  });
});
