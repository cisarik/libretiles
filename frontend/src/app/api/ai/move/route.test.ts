import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { generateTextMock, getLanguageModelMock, stepCountIsMock } = vi.hoisted(() => ({
  generateTextMock: vi.fn(),
  getLanguageModelMock: vi.fn(() => ({ provider: "test", modelId: "test" })),
  stepCountIsMock: vi.fn((n: number) => `stop-${n}`),
}));

vi.mock("ai", () => ({
  generateText: generateTextMock,
  stepCountIs: stepCountIsMock,
  tool: vi.fn((definition) => definition),
}));

vi.mock("@/lib/ai-runtimes", () => ({
  getLanguageModel: getLanguageModelMock,
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
    }
    return null;
  }),
  parseCatalogModelRows: (value: unknown) => value,
}));

import { POST } from "./route";

const MODEL_ID = "google/gemma-4-31b-it:free";
const PLACE_A = [{ row: 7, col: 7, letter: "A" }];
const WITNESS = [
  { row: 7, col: 7, letter: "R" },
  { row: 7, col: 8, letter: "A" },
  { row: 7, col: 9, letter: "T" },
  { row: 7, col: 10, letter: "E" },
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
  body: unknown;
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

function mockBackend(routes: Record<string, RouteSpec> = {}) {
  const catalog = routes.catalog?.body ?? [{ provider: "openrouter", model_id: MODEL_ID }];
  const context = routes.context?.body ?? defaultContext();
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
      "/ai-playability/",
      "/ai-model/",
    ];
    for (const suffix of suffixes) {
      if (url.endsWith(suffix) && routes[suffix]) {
        return jsonResponse(routes[suffix].body, routes[suffix].status ?? 200);
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
    generateTextMock.mockImplementation(searchWithPassText(true));
    getLanguageModelMock.mockClear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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
    expect(getLanguageModelMock).not.toHaveBeenCalled();
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
});
