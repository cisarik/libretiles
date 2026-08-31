import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  generateTextMock,
  getLanguageRuntimeMock,
  stepCountIsMock,
  trackerRecordUsageMock,
  trackerSnapshotMock,
} = vi.hoisted(() => {
  const trackerRecordUsageMock = vi.fn();
  const trackerSnapshotMock = vi.fn<
    () => { provider_requests: number; retry_after_seconds?: number }
  >(() => ({ provider_requests: 0 }));
  return {
    generateTextMock: vi.fn(),
    getLanguageRuntimeMock: vi.fn(async () => ({
      model: { provider: "test", modelId: "test" },
      tracker: {
        noteProviderRequest: vi.fn(),
        recordUsage: trackerRecordUsageMock,
        recordRetryAfter: vi.fn(),
        snapshot: trackerSnapshotMock,
      },
    })),
    stepCountIsMock: vi.fn((n: number) => `stop-${n}`),
    trackerRecordUsageMock,
    trackerSnapshotMock,
  };
});

vi.mock("ai", () => ({
  generateText: generateTextMock,
  stepCountIs: stepCountIsMock,
  tool: vi.fn((definition) => definition),
}));

vi.mock("@/lib/ai-runtimes", () => ({
  getLanguageRuntime: getLanguageRuntimeMock,
  isLegalBackendTerminal: (value: unknown) =>
    typeof value === "object" && value !== null && "ok" in value && value.ok === true,
  normalizeProviderError: vi.fn((error: unknown) => {
    if (error && typeof error === "object" && "statusCode" in error) {
      const status = (error as { statusCode?: number }).statusCode;
      if (status === 429) {
        return {
          code: "provider_rate_limited",
          message:
            "This free rival is rate limited. Switch to another free rival or retry later.",
        };
      }
      if (status === 404) {
        return {
          code: "provider_unavailable",
          message:
            "This free rival is temporarily unavailable. Switch to another free rival or retry later.",
        };
      }
    }
    return null;
  }),
  parseCatalogModelRows: (value: unknown) => value,
}));

import { POST } from "./route";

const MODEL_ID = "google/gemma-4-31b-it:free";
const PLACE_A = [{ row: 7, col: 7, letter: "A" }];
const BACKEND_MOVE = [
  { row: 7, col: 6, letter: "A" },
  { row: 7, col: 7, letter: "T" },
];
const WITNESS = [
  { row: 7, col: 7, letter: "R" },
  { row: 7, col: 8, letter: "A" },
  { row: 7, col: 9, letter: "T" },
  { row: 7, col: 10, letter: "E" },
];
const SK_RANKED = [
  { row: 7, col: 7, letter: "Ľ" },
  { row: 7, col: 8, letter: "Á" },
  { row: 7, col: 9, letter: "Ť" },
];
const SK_WITNESS = [
  { row: 7, col: 7, letter: "O" },
  { row: 7, col: 8, letter: "S" },
  { row: 7, col: 9, letter: "?", blank_as: "Ľ" },
  { row: 7, col: 10, letter: "A" },
  { row: 7, col: 11, letter: "Ť" },
  { row: 7, col: 12, letter: "A" },
];

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
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

type RouteSpec = {
  body: unknown | ((callIndex: number, init?: RequestInit) => unknown);
  status?: number;
};

function defaultContext() {
  return {
    compact_state: "empty board",
    ai_state: { ai_rack: "ABCDEFG", human_score: 0, ai_score: 0 },
    is_first_move: true,
    ai_model_id: MODEL_ID,
    ai_move_max_output_tokens: 2000,
  };
}

function rankedPayload(
  score: number,
  placements = BACKEND_MOVE,
  complete = true,
) {
  return {
    status: "found",
    candidates: [
      {
        placements,
        words: ["AT"],
        score,
        tiles_used: placements.length,
        leave_value: 0,
      },
    ],
    search: {
      complete,
      nodes: complete ? 100 : 500_000,
      elapsed_ms: complete ? 5 : 750,
      unique_placements: 1,
      candidate_count: 1,
    },
  };
}

function mockBackend(routes: Record<string, RouteSpec> = {}) {
  const catalog = routes.catalog?.body ?? [{ provider: "openrouter", model_id: MODEL_ID }];
  const context = routes.context?.body ?? defaultContext();
  const routeCalls = new Map<string, number>();
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    void init;
    const url = String(input);
    if (url.endsWith("/api/catalog/models/")) {
      return jsonResponse(catalog, routes.catalog?.status ?? 200);
    }
    if (url.endsWith("/api/game/game-1/ai-context/")) {
      return jsonResponse(context, routes.context?.status ?? 200);
    }
    const suffixes = [
      "/validate-move/",
      "/ai-move/",
      "/ai-pass/",
      "/ai-exchange/",
      "/ai-candidates/",
      "/ai-playability/",
      "/ai-model/",
    ];
    for (const suffix of suffixes) {
      if (url.endsWith(suffix)) {
        const spec =
          routes[suffix] ??
          (suffix === "/ai-candidates/"
            ? {
                body: {
                  status: "none",
                  candidates: [],
                  search: {
                    complete: true,
                    nodes: 1,
                    elapsed_ms: 1,
                    unique_placements: 0,
                    candidate_count: 0,
                  },
                },
              }
            : null);
        if (spec) {
          const callIndex = routeCalls.get(suffix) ?? 0;
          routeCalls.set(suffix, callIndex + 1);
          const responseBody =
            typeof spec.body === "function"
              ? spec.body(callIndex, init)
              : spec.body;
          return jsonResponse(responseBody, spec.status ?? 200);
        }
      }
    }
    throw new Error(`Unexpected backend request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function fetchUrls(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map(([url]) => String(url));
}

function stepFinish(stepNumber: number) {
  return {
    stepNumber,
    toolCalls: [],
    usage: {},
    model: { provider: "openrouter", modelId: MODEL_ID },
    response: { modelId: MODEL_ID },
  };
}

async function invokeValidateMove(
  opts: { tools?: { validateMove?: { execute?: (input: unknown) => Promise<unknown> } } },
  placements = PLACE_A,
) {
  const execute = opts.tools?.validateMove?.execute;
  if (!execute) throw new Error("validateMove.execute missing");
  await execute({ placements });
}

function searchWithPassText(valid = true) {
  return async (opts: {
    tools?: { validateMove?: { execute?: (input: unknown) => Promise<unknown> } };
    onStepFinish?: (step: ReturnType<typeof stepFinish>) => void;
  }) => {
    if (valid) await invokeValidateMove(opts);
    opts.onStepFinish?.(stepFinish(0));
    return {
      text: JSON.stringify({ action: "pass" }),
      steps: [stepFinish(0)],
    };
  };
}

function hangUntilAbort(
  opts: {
    abortSignal?: AbortSignal;
    onStepFinish?: (step: ReturnType<typeof stepFinish>) => void;
  },
  completedSteps = 0,
) {
  for (let i = 0; i < completedSteps; i += 1) {
    opts.onStepFinish?.(stepFinish(i));
  }
  return new Promise<never>((_, reject) => {
    const signal = opts.abortSignal;
    const fail = () => reject(new DOMException("Timeout", "AbortError"));
    if (!signal) {
      reject(new Error("abortSignal missing"));
      return;
    }
    if (signal.aborted) {
      fail();
      return;
    }
    signal.addEventListener("abort", fail, { once: true });
  });
}

async function waitForGenerateText() {
  for (let i = 0; i < 100; i += 1) {
    if (generateTextMock.mock.calls.length > 0) return;
    await Promise.resolve();
  }
  throw new Error("generateText was not called");
}

async function collectEvents(req: NextRequest = request()) {
  const response = await POST(req);
  expect(response.headers.get("content-type")).toContain("text/event-stream");
  const events = parseSse(await response.text());
  expect(JSON.stringify(events)).not.toMatch(
    /charge-ai-turn|credit_balance|creditBalance|charged_|billing/i,
  );
  return {
    events,
    done: events.find((event) => event.type === "done"),
    error: events.find((event) => event.type === "error"),
  };
}

async function runRoute(req: NextRequest = request()) {
  const collected = await collectEvents(req);
  expect(collected.done).toBeDefined();
  return collected;
}

describe("POST /api/ai/move", () => {
  beforeEach(() => {
    generateTextMock.mockReset();
    stepCountIsMock.mockClear();
    trackerRecordUsageMock.mockClear();
    trackerSnapshotMock.mockReset();
    trackerSnapshotMock.mockReturnValue({ provider_requests: 0 });
    generateTextMock.mockImplementation(searchWithPassText(true));
    getLanguageRuntimeMock.mockClear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("applies a place without a billing request or monetary done fields", async () => {
    const fetchMock = mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });

    const { done } = await runRoute();
    expect(done?.action).toBe("place");
    expect(done?.completion_source).toBe("provider_candidate");
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/billing/charge-ai-turn/"),
      expect.anything(),
    );
  });

  it("ignores free-form action:pass when a valid tracked candidate exists", async () => {
    const fetchMock = mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });

    const { done } = await runRoute();
    expect(done?.action).toBe("place");
    expect(done?.completion_source).toBe("provider_candidate");
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-pass/"))).toBe(false);
  });

  it("applies a tracked candidate when the model returns malformed text", async () => {
    generateTextMock.mockImplementation(async (opts) => {
      await invokeValidateMove(opts);
      return { text: "not-json", steps: [stepFinish(0)] };
    });
    mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });

    const { done } = await runRoute();
    expect(done?.action).toBe("place");
    expect(done?.completion_source).toBe("provider_candidate");
  });

  it("prefers a backend score 46 move over a provider score 10 move", async () => {
    const fetchMock = mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 10, words: [{ word: "A", valid: true }] },
      },
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const { done } = await runRoute();

    expect(done?.completion_source).toBe("backend_ranked_candidate");
    expect(done?.best_score).toBe(46);
    const moveCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/ai-move/"),
    );
    expect(JSON.parse(String(moveCall?.[1]?.body))).toMatchObject({
      placements: BACKEND_MOVE,
      ai_metadata: { completion_source: "backend_ranked_candidate" },
    });
  });

  it("prefers a provider score 50 move over a backend score 46 move", async () => {
    const fetchMock = mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 50, words: [{ word: "A", valid: true }] },
      },
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 50, words: [{ word: "A", score: 50 }] },
      },
    });

    const { done } = await runRoute();

    expect(done?.completion_source).toBe("provider_candidate");
    expect(done?.best_score).toBe(50);
    const moveCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/ai-move/"),
    );
    expect(JSON.parse(String(moveCall?.[1]?.body))).toMatchObject({
      placements: PLACE_A,
      ai_metadata: { completion_source: "provider_candidate" },
    });
  });

  it("uses server order when backend and provider scores are equal", async () => {
    const fetchMock = mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 46, words: [{ word: "A", valid: true }] },
      },
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const { done } = await runRoute();

    expect(done?.completion_source).toBe("backend_ranked_candidate");
    const moveCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/ai-move/"),
    );
    expect(JSON.parse(String(moveCall?.[1]?.body)).placements).toEqual(BACKEND_MOVE);
  });

  it("resolves a normal prose-only generation with a ranked backend move", async () => {
    generateTextMock.mockResolvedValue({ text: "I would play AT.", steps: [stepFinish(0)] });
    const fetchMock = mockBackend({
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const { done } = await runRoute();

    expect(done?.completion_source).toBe("backend_ranked_candidate");
    expect(fetchUrls(fetchMock).filter((url) => url.endsWith("/ai-candidates/"))).toHaveLength(1);
    expect(fetchUrls(fetchMock).some((url) => url.endsWith("/ai-playability/"))).toBe(false);
  });

  it("uses a ranked candidate even when the bounded backend search is incomplete", async () => {
    generateTextMock.mockResolvedValue({ text: "search ended", steps: [stepFinish(0)] });
    mockBackend({
      "/ai-candidates/": { body: rankedPayload(46, BACKEND_MOVE, false) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const { done } = await runRoute();

    expect(done?.completion_source).toBe("backend_ranked_candidate");
    expect(done?.action).toBe("place");
  });

  it.each([
    ["none", { status: "none", candidates: [] }],
    ["indeterminate", { status: "indeterminate", candidates: [] }],
    ["error", { ok: false, error: "ranked search unavailable" }],
  ])("keeps old playability authority when ranked status is %s", async (_label, payload) => {
    generateTextMock.mockResolvedValue({ text: "no tool", steps: [stepFinish(0)] });
    const fetchMock = mockBackend({
      "/ai-candidates/": { body: payload },
      "/ai-playability/": {
        body: {
          status: "none",
          witness: null,
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 1, elapsed_ms: 1 },
        },
      },
      "/ai-pass/": { body: { ok: true, action: "pass" } },
    });

    const { done } = await runRoute();

    expect(done?.completion_source).toBe("genuine_no_move_pass");
    expect(fetchUrls(fetchMock).filter((url) => url.endsWith("/ai-candidates/"))).toHaveLength(1);
    expect(fetchUrls(fetchMock).filter((url) => url.endsWith("/ai-playability/"))).toHaveLength(1);
  });

  it("keeps endpoint failures in the provider fallback lane without backend-only play", async () => {
    generateTextMock.mockRejectedValue(
      Object.assign(new Error("No endpoints found for stealth/model"), { statusCode: 404 }),
    );
    const fetchMock = mockBackend({
      "/ai-candidates/": { body: rankedPayload(46) },
    });

    const { done, error } = await collectEvents();

    expect(done).toBeUndefined();
    expect(error?.code).toBe("provider_unavailable");
    expect(fetchUrls(fetchMock).some((url) => url.endsWith("/ai-candidates/"))).toBe(false);
    expect(fetchUrls(fetchMock).some((url) => url.endsWith("/ai-move/"))).toBe(false);
  });

  it("falls through a stale ranked candidate to the old playability witness", async () => {
    generateTextMock.mockResolvedValue({ text: "no tool", steps: [stepFinish(0)] });
    const fetchMock = mockBackend({
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: (callIndex: number) =>
          callIndex === 0
            ? { ok: false, code: "state_conflict", error: "stale" }
            : {
                ok: true,
                action: "place",
                points: 8,
                words: [{ word: "RATE", score: 8 }],
              },
      },
      "/ai-playability/": {
        body: {
          status: "found",
          witness: { placements: WITNESS, words: ["RATE"], total_score: 8 },
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 4, elapsed_ms: 2 },
        },
      },
    });

    const { done } = await runRoute(request({ max_steps: 5 }));

    expect(done?.completion_source).toBe("backend_witness_rescue");
    expect(fetchUrls(fetchMock).filter((url) => url.endsWith("/ai-move/"))).toHaveLength(2);
    expect(fetchUrls(fetchMock).filter((url) => url.endsWith("/ai-candidates/"))).toHaveLength(1);
  });

  it("merges ranked choices on a generic error only after tracking a valid provider move", async () => {
    generateTextMock.mockImplementation(async (opts) => {
      await invokeValidateMove(opts);
      throw new Error("generic SDK failure");
    });
    const fetchMock = mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 10, words: [{ word: "A", valid: true }] },
      },
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const { done } = await runRoute();

    expect(done?.completion_source).toBe("backend_ranked_candidate");
    expect(done?.terminal_cause).toBe("generic_error_fallback");
    expect(fetchUrls(fetchMock).filter((url) => url.endsWith("/ai-candidates/"))).toHaveLength(1);
    expect(generateTextMock).toHaveBeenCalledTimes(1);
  });

  it("rescues a generic runtime error with a backend-ranked candidate without a tracked provider candidate", async () => {
    generateTextMock.mockRejectedValue(new Error("generic SDK failure"));
    const fetchMock = mockBackend({
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const { done } = await runRoute();

    expect(done?.completion_source).toBe("backend_ranked_candidate");
    expect(done?.terminal_cause).toBe("generic_error_fallback");
    expect(fetchUrls(fetchMock).filter((url) => url.endsWith("/ai-candidates/"))).toHaveLength(1);
    expect(fetchUrls(fetchMock).filter((url) => url.endsWith("/ai-move/"))).toHaveLength(1);
    expect(generateTextMock).toHaveBeenCalledTimes(1);
  });

  it("rescues a generic runtime error with a Slovak Unicode witness when ranked candidates are empty", async () => {
    generateTextMock.mockRejectedValue(new Error("generic SDK failure"));
    const fetchMock = mockBackend({
      "/ai-candidates/": {
        body: {
          status: "none",
          candidates: [],
          search: {
            complete: true,
            nodes: 1,
            elapsed_ms: 1,
            unique_placements: 0,
            candidate_count: 0,
          },
        },
      },
      "/ai-playability/": {
        body: {
          status: "found",
          witness: { placements: SK_WITNESS, words: ["OSĽAŤA"], total_score: 12 },
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 4, elapsed_ms: 2 },
        },
      },
      "/ai-move/": {
        body: {
          ok: true,
          action: "place",
          points: 12,
          words: [{ word: "OSĽAŤA", score: 12 }],
        },
      },
    });

    const { done, error } = await collectEvents();

    expect(error).toBeUndefined();
    expect(done?.completion_source).toBe("backend_witness_rescue");
    expect(done?.terminal_cause).toBe("backend_witness_rescue");
    expect(error?.code).not.toBe("stale_witness");
    expect(generateTextMock).toHaveBeenCalledTimes(1);
    const moveCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/ai-move/"),
    );
    const moveBody = JSON.parse(String(moveCall?.[1]?.body)) as {
      placements: Array<{ letter?: string; blank_as?: string }>;
    };
    expect(moveBody.placements).toEqual(SK_WITNESS);
    expect(JSON.stringify(moveBody.placements)).toContain("Ľ");
  });

  it("emits a bounded terminal when backend rescue itself fails", async () => {
    generateTextMock.mockRejectedValue(new Error("generic SDK failure"));
    const fetchMock = mockBackend({
      "/ai-candidates/": {
        body: {
          status: "none",
          candidates: [],
          search: {
            complete: true,
            nodes: 1,
            elapsed_ms: 1,
            unique_placements: 0,
            candidate_count: 0,
          },
        },
      },
      "/ai-playability/": {
        body: () => {
          throw new Error("secret-rack-and-token");
        },
      },
    });

    const { done, error, events } = await collectEvents();

    expect(done).toBeUndefined();
    expect(["ai_move_internal_error", "playability_unknown"]).toContain(error?.code);
    expect(typeof error?.terminal_cause).toBe("string");
    expect(error?.terminal_cause).not.toBe("error");
    expect(error?.error).not.toBe("AI move failed");
    expect(JSON.stringify(events)).not.toContain("secret-rack-and-token");
    expect(JSON.stringify(error)).not.toContain("secret-rack-and-token");
    expect(generateTextMock).toHaveBeenCalledTimes(1);
    expect(fetchUrls(fetchMock).some((url) => url.endsWith("/ai-move/"))).toBe(false);
  });

  it("applies a pass without a billing request after a genuine none probe", async () => {
    generateTextMock.mockImplementation(searchWithPassText(false));
    const fetchMock = mockBackend({
      "/ai-playability/": {
        body: {
          status: "none",
          witness: null,
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 1, elapsed_ms: 1 },
        },
      },
      "/ai-pass/": { body: { ok: true, action: "pass" } },
    });

    const { done } = await runRoute();
    expect(done?.action).toBe("pass");
    expect(done?.completion_source).toBe("genuine_no_move_pass");
    expect(fetchUrls(fetchMock).some((url) => url.includes("billing"))).toBe(false);
  });

  it("applies an exchange with probe letters when none and exchange is allowed", async () => {
    generateTextMock.mockImplementation(searchWithPassText(false));
    const fetchMock = mockBackend({
      "/ai-playability/": {
        body: {
          status: "none",
          witness: null,
          exchange_allowed: true,
          exchange_letters: ["Q", "J"],
          search: { complete: true, nodes: 1, elapsed_ms: 1 },
        },
      },
      "/ai-exchange/": { body: { ok: true, action: "exchange" } },
    });

    const { done } = await runRoute();
    expect(done?.action).toBe("exchange");
    expect(done?.completion_source).toBe("genuine_no_move_exchange");
    const exchangeCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/ai-exchange/"),
    );
    expect(exchangeCall?.[1]).toEqual(
      expect.objectContaining({
        body: expect.stringContaining('"letters":["Q","J"]'),
      }),
    );
  });

  it("disables AI SDK retries on the provider stream", async () => {
    mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });
    await runRoute();
    expect(generateTextMock).toHaveBeenCalledWith(
      expect.objectContaining({ maxRetries: 0, temperature: 0.15 }),
    );
  });

  it("reports provider_requests_used in terminal metadata", async () => {
    generateTextMock.mockImplementation(async (opts) => {
      await invokeValidateMove(opts);
      opts.onStepFinish?.(stepFinish(0));
      opts.onStepFinish?.(stepFinish(1));
      return {
        text: "{}",
        steps: [stepFinish(0), stepFinish(1)],
      };
    });
    mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });

    const { done } = await runRoute();
    expect(done?.provider_requests_used).toBe(2);
    expect(done?.turn_provider_requests_used).toBe(2);
  });

  it("uses tracked failed HTTP count and bounded Retry-After on provider errors", async () => {
    trackerSnapshotMock.mockReturnValue({
      provider_requests: 4,
      retry_after_seconds: 17,
    });
    generateTextMock.mockRejectedValue(
      Object.assign(new Error("rate limited"), { statusCode: 429 }),
    );
    mockBackend();

    const { done, error } = await collectEvents();
    expect(done).toBeUndefined();
    expect(error).toMatchObject({
      type: "error",
      code: "provider_rate_limited",
      provider_requests_used: 4,
      turn_provider_requests_used: 4,
      retry_after_seconds: 17,
    });
  });

  it("repairs a stale requested model onto catalog row 1 without PATCHing", async () => {
    const fetchMock = mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });

    const { done } = await runRoute(
      request({ model_id: "openai/gpt-5-mini", runtime_model_id: "openai/gpt-5-mini" }),
    );
    expect(done?.action).toBe("place");
    expect(done?.runtime_model).toBe(MODEL_ID);
    const calls = fetchMock.mock.calls as Array<[string | URL | Request, RequestInit?]>;
    expect(calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
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
    expect(getLanguageRuntimeMock).not.toHaveBeenCalled();
  });

  it("applies a tracked candidate on timeout and does not probe", async () => {
    generateTextMock.mockImplementation(async (opts) => {
      await invokeValidateMove(opts);
      throw new DOMException("Timeout", "AbortError");
    });
    const fetchMock = mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });

    const { done } = await runRoute();
    expect(done?.action).toBe("place");
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-playability/"))).toBe(
      false,
    );
  });

  it("rescues a timeout without a candidate through the playability witness", async () => {
    generateTextMock.mockRejectedValue(new DOMException("Timeout", "AbortError"));
    const fetchMock = mockBackend({
      "/ai-playability/": {
        body: {
          status: "found",
          witness: { placements: WITNESS, words: ["RATE"], total_score: 8 },
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 4, elapsed_ms: 2 },
        },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 8, words: [{ word: "RATE", score: 8 }] },
      },
    });

    const { done } = await runRoute();
    expect(done?.action).toBe("place");
    expect(done?.completion_source).toBe("backend_witness_rescue");
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-playability/"))).toBe(
      true,
    );
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-pass/"))).toBe(false);
  });

  it("emits an error and makes no terminal call when playability is indeterminate", async () => {
    generateTextMock.mockImplementation(searchWithPassText(false));
    const fetchMock = mockBackend({
      "/ai-playability/": {
        body: {
          status: "indeterminate",
          witness: null,
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: false, nodes: 9, elapsed_ms: 2000 },
        },
      },
    });

    const { done, error } = await collectEvents();
    expect(done).toBeUndefined();
    expect(error?.type).toBe("error");
    expect(error?.code).toBe("playability_unknown");
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-pass/"))).toBe(false);
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-move/"))).toBe(false);
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-exchange/"))).toBe(false);
  });

  it("runs one temperature-0 repair when found and budget remains", async () => {
    generateTextMock
      .mockImplementationOnce(async (opts) => {
        opts.onStepFinish?.(stepFinish(0));
        return { text: "{}", steps: [stepFinish(0)] };
      })
      .mockImplementationOnce(async (opts) => {
        await invokeValidateMove(opts, WITNESS);
        opts.onStepFinish?.(stepFinish(0));
        opts.onStepFinish?.(stepFinish(1));
        return { text: "{}", steps: [stepFinish(0), stepFinish(1)] };
      });
    mockBackend({
      "/ai-playability/": {
        body: {
          status: "found",
          witness: { placements: WITNESS, words: ["RATE"], total_score: 8 },
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 4, elapsed_ms: 2 },
        },
      },
      "/validate-move/": {
        body: { valid: true, total_score: 8, words: [{ word: "RATE", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 8, words: [{ word: "RATE", score: 8 }] },
      },
    });

    const { done } = await runRoute();
    expect(done?.action).toBe("place");
    expect(done?.completion_source).toBe("repair_candidate");
    expect(done?.repair_attempted).toBe(true);
    expect(done?.turn_provider_requests_used).toBe(3);
    expect(generateTextMock).toHaveBeenCalledTimes(2);
    expect(generateTextMock.mock.calls[1][0]).toEqual(
      expect.objectContaining({ temperature: 0, maxRetries: 0 }),
    );
    expect(stepCountIsMock).toHaveBeenCalledWith(8);
    expect(stepCountIsMock).toHaveBeenCalledWith(2);
  });

  it("rescues the witness directly when remaining step budget is under 2", async () => {
    generateTextMock.mockImplementation(async (opts) => {
      for (let step = 0; step < 9; step += 1) opts.onStepFinish?.(stepFinish(step));
      return { text: "{}", steps: Array.from({ length: 9 }, (_, step) => stepFinish(step)) };
    });
    const fetchMock = mockBackend({
      "/ai-playability/": {
        body: {
          status: "found",
          witness: { placements: WITNESS, words: ["RATE"], total_score: 8 },
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 4, elapsed_ms: 2 },
        },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 8, words: [{ word: "RATE", score: 8 }] },
      },
    });

    const { done } = await runRoute();
    expect(done?.action).toBe("place");
    expect(done?.completion_source).toBe("backend_witness_rescue");
    expect(done?.repair_attempted).toBe(false);
    expect(generateTextMock).toHaveBeenCalledTimes(1);
    expect(fetchUrls(fetchMock).filter((url) => url.includes("/ai-move/"))).toHaveLength(1);
  });

  it("emits a guard error without retrying a 409 non-scoring terminal", async () => {
    generateTextMock.mockImplementation(searchWithPassText(false));
    const fetchMock = mockBackend({
      "/ai-playability/": {
        body: {
          status: "none",
          witness: null,
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 1, elapsed_ms: 1 },
        },
      },
      "/ai-pass/": {
        status: 409,
        body: {
          ok: false,
          error: "A legal scoring move exists",
          code: "legal_scoring_move_exists",
        },
      },
    });

    const { done, error } = await collectEvents();
    expect(done).toBeUndefined();
    expect(error?.code).toBe("legal_scoring_move_exists");
    expect(fetchUrls(fetchMock).filter((url) => url.includes("/ai-pass/"))).toHaveLength(1);
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-move/"))).toBe(false);
  });

  it("caps the initial search at max_steps-2 and never exceeds the grant", async () => {
    mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });
    await runRoute(request({ max_steps: 10 }));
    expect(stepCountIsMock).toHaveBeenCalledWith(8);
    expect(generateTextMock.mock.calls[0][0].stopWhen).toBe("stop-8");
  });

  it("uses omitted-field defaults of 120 seconds and 50 steps", async () => {
    mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });
    const { events } = await runRoute(
      request({ timeout: undefined, max_steps: undefined }),
    );
    expect(events).toContainEqual(
      expect.objectContaining({
        type: "thinking",
        timeout: 120,
        max_steps: 50,
      }),
    );
    expect(stepCountIsMock).toHaveBeenCalledWith(48);
  });

  it("accepts a positive sub-15-second tail grant without inflating it", async () => {
    mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });
    const { events } = await runRoute(request({ timeout: 7, max_steps: 5 }));
    expect(events).toContainEqual(
      expect.objectContaining({
        type: "thinking",
        timeout: 7,
        max_steps: 5,
      }),
    );
    expect(stepCountIsMock).toHaveBeenCalledWith(3);
  });

  it("sends rack_owner ai on validateMove tool POSTs", async () => {
    const fetchMock = mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });
    await runRoute();
    const validateCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes("/validate-move/"),
    );
    expect(validateCalls.length).toBeGreaterThan(0);
    for (const [, init] of validateCalls) {
      const body = JSON.parse(String((init as RequestInit | undefined)?.body));
      expect(body.rack_owner).toBe("ai");
    }
  });

  it("forces validateMove on step 1 and unlocks finishMove after a valid candidate", async () => {
    mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });
    await runRoute();
    const opts = generateTextMock.mock.calls[0][0] as {
      prepareStep: (input: { stepNumber: number }) => {
        activeTools: string[];
        toolChoice?: { type: string; toolName: string };
      };
    };
    const first = opts.prepareStep({ stepNumber: 0 });
    expect(first.activeTools).toEqual(["validateMove"]);
    expect(first.toolChoice).toEqual({ type: "tool", toolName: "validateMove" });
    const later = opts.prepareStep({ stepNumber: 1 });
    expect(later.activeTools).toEqual(["validateMove", "finishMove"]);
  });

  it("keeps existing done fields while adding optional terminal diagnostics", async () => {
    mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });
    const { done } = await runRoute();
    expect(done).toEqual(
      expect.objectContaining({
        type: "done",
        action: "place",
        provider_path: "openrouter",
        runtime_model: MODEL_ID,
        provider_requests_used: expect.any(Number),
        turn_provider_requests_used: expect.any(Number),
        completion_source: "provider_candidate",
        repair_attempted: false,
        terminal_cause: expect.any(String),
      }),
    );
  });

  it("does not send Collins as the sole authority for a slovak context", async () => {
    mockBackend({
      context: {
        body: {
          ...defaultContext(),
          lexicon_id: "slovak",
          variant: "slovak",
          tile_points: { A: 1, Á: 4, X: 10, "?": 0 },
        },
      },
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });
    await runRoute();
    const opts = generateTextMock.mock.calls[0][0] as {
      system: string;
      prompt: string;
    };
    expect(opts.system).not.toMatch(/Collins Scrabble Words \(2019\)/);
    expect(opts.system).toMatch(/shipped Slovak lexicon/i);
    expect(opts.prompt).toContain("Á=4");
    expect(opts.prompt).not.toContain("Q=10");
  });

  it("keeps ranked Unicode diacritic placements instead of dropping the candidate", async () => {
    generateTextMock.mockResolvedValue({ text: "I would play ĽÁŤ.", steps: [stepFinish(0)] });
    const fetchMock = mockBackend({
      "/ai-candidates/": { body: rankedPayload(46, SK_RANKED) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "ĽÁŤ", score: 46 }] },
      },
    });

    const { done } = await runRoute();

    expect(done?.completion_source).toBe("backend_ranked_candidate");
    const moveCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/ai-move/"),
    );
    expect(JSON.parse(String(moveCall?.[1]?.body))).toMatchObject({
      placements: SK_RANKED,
      ai_metadata: { completion_source: "backend_ranked_candidate" },
    });
  });

  it("rescues a Slovak diacritic playability witness instead of stale_witness", async () => {
    generateTextMock.mockRejectedValue(new DOMException("Timeout", "AbortError"));
    const fetchMock = mockBackend({
      "/ai-playability/": {
        body: {
          status: "found",
          witness: { placements: SK_WITNESS, words: ["OSĽAŤA"], total_score: 12 },
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 4, elapsed_ms: 2 },
        },
      },
      "/ai-move/": {
        body: {
          ok: true,
          action: "place",
          points: 12,
          words: [{ word: "OSĽAŤA", score: 12 }],
        },
      },
    });

    const { done, error } = await collectEvents();

    expect(error).toBeUndefined();
    expect(done?.action).toBe("place");
    expect(done?.completion_source).toBe("backend_witness_rescue");
    expect(error?.code).not.toBe("stale_witness");
    const moveCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/ai-move/"),
    );
    expect(JSON.parse(String(moveCall?.[1]?.body))).toMatchObject({
      placements: SK_WITNESS,
      ai_metadata: { completion_source: "backend_witness_rescue" },
    });
  });

  it.each([
    ["1", [{ row: 7, col: 7, letter: "A" }, { row: 7, col: 8, letter: "1" }]],
    ["😀", [{ row: 7, col: 7, letter: "A" }, { row: 7, col: 8, letter: "😀" }]],
  ])(
    "skips a ranked candidate when a placement letter is %s",
    async (_label, placements) => {
      generateTextMock.mockResolvedValue({ text: "no tool", steps: [stepFinish(0)] });
      const fetchMock = mockBackend({
        "/ai-candidates/": { body: rankedPayload(46, placements) },
        "/ai-playability/": {
          body: {
            status: "none",
            witness: null,
            exchange_allowed: false,
            exchange_letters: [],
            search: { complete: true, nodes: 1, elapsed_ms: 1 },
          },
        },
        "/ai-pass/": { body: { ok: true, action: "pass" } },
      });

      const { done } = await runRoute();

      expect(done?.completion_source).toBe("genuine_no_move_pass");
      expect(fetchUrls(fetchMock).some((url) => url.endsWith("/ai-move/"))).toBe(false);
    },
  );

  it("test_no_progress_deadline_commits_ranked_candidate_when_model_produces_nothing", async () => {
    vi.useFakeTimers();
    generateTextMock.mockImplementation(async (opts) => hangUntilAbort(opts));
    const fetchMock = mockBackend({
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const pending = collectEvents(
      request({ timeout: 30, no_provider_progress_deadline: 5 }),
    );
    await waitForGenerateText();
    await vi.advanceTimersByTimeAsync(5_000);
    await Promise.resolve();
    const { done } = await pending;

    expect(done?.action).toBe("place");
    expect(done?.completion_source).toBe("backend_ranked_candidate");
    expect(done?.timed_out).toBe(false);
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-pass/"))).toBe(false);
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-exchange/"))).toBe(false);
  });

  it("test_deadline_does_not_fire_when_model_produced_a_valid_candidate", async () => {
    vi.useFakeTimers();
    generateTextMock.mockImplementation(async (opts) => {
      await invokeValidateMove(opts);
      return hangUntilAbort(opts);
    });
    mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 50, words: [{ word: "A", valid: true }] },
      },
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 50, words: [{ word: "A", score: 50 }] },
      },
    });

    const pending = collectEvents(
      request({ timeout: 30, no_provider_progress_deadline: 5 }),
    );
    await waitForGenerateText();
    const signal = (
      generateTextMock.mock.calls[0][0] as { abortSignal: AbortSignal }
    ).abortSignal;
    await vi.advanceTimersByTimeAsync(2_500);
    await Promise.resolve();
    expect(signal.aborted).toBe(true);
    const { done } = await pending;

    expect(done?.completion_source).toBe("provider_candidate");
    expect(done?.terminal_cause).not.toBe("no_provider_progress_deadline");
    expect(done?.auto_finalized).toBe(true);
  });

  it("test_deadline_does_not_fire_without_a_ranked_candidate", async () => {
    vi.useFakeTimers();
    generateTextMock.mockImplementation(async (opts) => hangUntilAbort(opts));
    mockBackend({
      "/ai-playability/": {
        body: {
          status: "found",
          witness: { placements: WITNESS, words: ["RATE"], total_score: 8 },
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 4, elapsed_ms: 2 },
        },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 8, words: [{ word: "RATE", score: 8 }] },
      },
    });

    const pending = collectEvents(
      request({ timeout: 12, no_provider_progress_deadline: 4 }),
    );
    await waitForGenerateText();
    const signal = (
      generateTextMock.mock.calls[0][0] as { abortSignal: AbortSignal }
    ).abortSignal;
    await vi.advanceTimersByTimeAsync(4_000);
    await Promise.resolve();
    expect(signal.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(8_000);
    const { done } = await pending;

    expect(signal.aborted).toBe(true);
    expect(done?.completion_source).toBe("backend_witness_rescue");
    expect(done?.terminal_cause).not.toBe("no_provider_progress_deadline");
  });

  it("test_deadline_never_causes_pass_or_exchange_while_probe_found", async () => {
    vi.useFakeTimers();
    generateTextMock.mockImplementation(async (opts) => hangUntilAbort(opts));
    const fetchMock = mockBackend({
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-playability/": {
        body: {
          status: "found",
          witness: { placements: WITNESS, words: ["RATE"], total_score: 8 },
          exchange_allowed: false,
          exchange_letters: [],
          search: { complete: true, nodes: 4, elapsed_ms: 2 },
        },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const pending = collectEvents(
      request({ timeout: 30, no_provider_progress_deadline: 5 }),
    );
    await waitForGenerateText();
    await vi.advanceTimersByTimeAsync(5_000);
    await Promise.resolve();
    const { done } = await pending;

    expect(done?.action).toBe("place");
    expect(done?.completion_source).toBe("backend_ranked_candidate");
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-pass/"))).toBe(false);
    expect(fetchUrls(fetchMock).some((url) => url.includes("/ai-exchange/"))).toBe(false);
    expect(fetchUrls(fetchMock).filter((url) => url.includes("/ai-playability/"))).toHaveLength(
      0,
    );
  });

  it("test_deadline_terminal_reports_backend_ranked_candidate_with_no_progress_cause", async () => {
    vi.useFakeTimers();
    generateTextMock.mockImplementation(async (opts) => hangUntilAbort(opts));
    mockBackend({
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const pending = collectEvents(
      request({ timeout: 30, no_provider_progress_deadline: 5 }),
    );
    await waitForGenerateText();
    await vi.advanceTimersByTimeAsync(5_000);
    await Promise.resolve();
    const { done } = await pending;

    expect(done?.completion_source).toBe("backend_ranked_candidate");
    expect(done?.terminal_cause).toBe("no_provider_progress_deadline");
    expect(done?.action).toBe("place");
  });

  it("test_deadline_respects_repair_reserve_and_hard_timeout", async () => {
    vi.useFakeTimers();
    generateTextMock.mockImplementation(async (opts) => hangUntilAbort(opts));
    mockBackend({
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const pending = collectEvents(
      request({ timeout: 30, max_steps: 10, no_provider_progress_deadline: 100 }),
    );
    await waitForGenerateText();
    expect(stepCountIsMock).toHaveBeenCalledWith(8);
    const signal = (
      generateTextMock.mock.calls[0][0] as { abortSignal: AbortSignal }
    ).abortSignal;
    await vi.advanceTimersByTimeAsync(20_000);
    await Promise.resolve();
    expect(signal.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(8_000);
    const { done, events } = await pending;

    expect(events).toContainEqual(
      expect.objectContaining({
        type: "thinking",
        timeout: 30,
        no_provider_progress_deadline: 28,
      }),
    );
    expect(done?.completion_source).toBe("backend_ranked_candidate");
    expect(done?.timed_out).toBe(false);
    expect(signal.aborted).toBe(true);
  });

  it("test_deadline_is_clamped_and_never_exceeds_attempt_timeout", async () => {
    generateTextMock.mockImplementation(searchWithPassText(true));
    mockBackend({
      "/validate-move/": {
        body: { valid: true, total_score: 2, words: [{ word: "A", valid: true }] },
      },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 2, words: [{ word: "A", score: 2 }] },
      },
    });

    const oversized = await runRoute(
      request({ timeout: 7, max_steps: 5, no_provider_progress_deadline: 100 }),
    );
    expect(oversized.events).toContainEqual(
      expect.objectContaining({
        type: "thinking",
        timeout: 7,
        no_provider_progress_deadline: 5,
      }),
    );

    const omitted = await runRoute(
      request({ timeout: 30, max_steps: 10, no_provider_progress_deadline: undefined }),
    );
    expect(omitted.events).toContainEqual(
      expect.objectContaining({
        type: "thinking",
        timeout: 30,
        no_provider_progress_deadline: 20,
      }),
    );

    const explicit = await runRoute(
      request({ timeout: 30, max_steps: 10, no_provider_progress_deadline: 3 }),
    );
    expect(explicit.events).toContainEqual(
      expect.objectContaining({
        type: "thinking",
        timeout: 30,
        no_provider_progress_deadline: 3,
      }),
    );
  });

  it("test_provider_accounting_is_exact_when_an_in_flight_call_is_abandoned", async () => {
    vi.useFakeTimers();
    generateTextMock.mockImplementation(async (opts) => hangUntilAbort(opts, 1));
    mockBackend({
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const pending = collectEvents(
      request({ timeout: 30, no_provider_progress_deadline: 5 }),
    );
    await waitForGenerateText();
    await vi.advanceTimersByTimeAsync(5_000);
    await Promise.resolve();
    const { done } = await pending;

    expect(done?.provider_requests_used).toBe(1);
    expect(done?.turn_provider_requests_used).toBe(1);
    expect(done?.completion_source).toBe("backend_ranked_candidate");
  });

  it("test_english_ranked_rescue_behaviour_is_unchanged_by_the_deadline", async () => {
    generateTextMock.mockResolvedValue({ text: "I would play AT.", steps: [stepFinish(0)] });
    mockBackend({
      "/ai-candidates/": { body: rankedPayload(46) },
      "/ai-move/": {
        body: { ok: true, action: "place", points: 46, words: [{ word: "AT", score: 46 }] },
      },
    });

    const { done } = await runRoute(
      request({ timeout: 30, no_provider_progress_deadline: 20 }),
    );

    expect(done?.action).toBe("place");
    expect(done?.completion_source).toBe("backend_ranked_candidate");
    expect(done?.terminal_cause).not.toBe("no_provider_progress_deadline");
    const opts = generateTextMock.mock.calls[0][0] as { system: string };
    expect(opts.system).toMatch(/Collins Scrabble Words 2019/);
  });

  it("does not call generateText when Django ai-context returns HTTP 429", async () => {
    mockBackend({
      context: {
        status: 429,
        body: { detail: "Request was throttled." },
      },
    });

    const collected = await collectEvents();
    expect(generateTextMock).not.toHaveBeenCalled();
    expect(getLanguageRuntimeMock).not.toHaveBeenCalled();
    expect(collected.error).toBeDefined();
  });
});
