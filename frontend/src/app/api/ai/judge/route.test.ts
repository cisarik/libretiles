import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { generateTextMock, getLanguageRuntimeMock, trackerRecordUsageMock } =
  vi.hoisted(() => {
    const trackerRecordUsageMock = vi.fn();
    return {
      generateTextMock: vi.fn(),
      getLanguageRuntimeMock: vi.fn(
        async (provider?: string, modelId?: string) => ({
          model: {
            provider: provider ?? "",
            modelId: modelId ?? "",
          },
          tracker: {
            noteProviderRequest: vi.fn(),
            recordUsage: trackerRecordUsageMock,
            recordRetryAfter: vi.fn(),
            snapshot: vi.fn(() => ({ provider_requests: 1 })),
          },
        }),
      ),
      trackerRecordUsageMock,
    };
  });

vi.mock("ai", () => ({ generateText: generateTextMock }));

vi.mock("@/lib/ai-runtimes", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ai-runtimes")>();
  return {
    ...actual,
    getLanguageRuntime: getLanguageRuntimeMock,
  };
});

import { POST } from "./route";

const NEWEST_CATALOG = [
  { provider: "openrouter", model_id: "z-ai/glm-5.2:free" },
  { provider: "openrouter", model_id: "nvidia/nemotron-3-super-120b-a12b:free" },
  { provider: "openrouter", model_id: "google/gemma-4-26b-a4b-it:free" },
  { provider: "nvidia-nim", model_id: "nvidia/nemotron-3-super-120b-a12b" },
  { provider: "openrouter", model_id: "google/gemma-4-31b-it:free" },
];

const SYNTHETIC_BEARER = "test-judge-token";
/** Must match the module constants in ./route.ts */
const MAX_JUDGE_WORDS = 12;
const MAX_JUDGE_WORD_LENGTH = 15;

function judgeRequest(
  modelId?: string,
  extra: Record<string, unknown> = {},
  authorization: string | null = `Bearer ${SYNTHETIC_BEARER}`,
): NextRequest {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authorization !== null) {
    headers.Authorization = authorization;
  }
  return new NextRequest("http://localhost/api/ai/judge", {
    method: "POST",
    headers,
    body: JSON.stringify({
      words: ["QI", "ZA"],
      ...(modelId === undefined ? {} : { model_id: modelId }),
      ...extra,
    }),
  });
}

function validPayload(text: string) {
  return {
    text,
    usage: { inputTokens: 12, outputTokens: 8, totalTokens: 20 },
  };
}

describe("POST /api/ai/judge", () => {
  beforeEach(() => {
    generateTextMock.mockReset();
    generateTextMock.mockImplementation(async () => {
      throw Object.assign(new Error("provider down"), { statusCode: 503 });
    });
    getLanguageRuntimeMock.mockReset();
    getLanguageRuntimeMock.mockImplementation(
      async (provider?: string, modelId?: string) => {
        let usageRecorded = false;
        return {
          model: { provider: provider ?? "", modelId: modelId ?? "" },
          tracker: {
            noteProviderRequest: vi.fn(),
            recordUsage: vi.fn((usage: unknown) => {
              trackerRecordUsageMock(usage);
              usageRecorded = true;
            }),
            recordRetryAfter: vi.fn(),
            snapshot: vi.fn(() => ({
              provider_requests: 1,
              ...(usageRecorded
                ? {
                    usage: {
                      input_tokens: 12,
                      output_tokens: 8,
                      total_tokens: 20,
                    },
                  }
                : {}),
            })),
          },
        };
      },
    );
    trackerRecordUsageMock.mockClear();
  });

  it("walks the newest-first queue when the first model fails", async () => {
    stubJudgeBackend();
    const order: Array<[string, string]> = [];
    getLanguageRuntimeMock.mockImplementation(async (provider?: string, modelId?: string) => {
      order.push([provider ?? "", modelId ?? ""]);
      let usageRecorded = false;
      return {
        model: { provider: provider ?? "", modelId: modelId ?? "" },
        tracker: {
          noteProviderRequest: vi.fn(),
          recordUsage: vi.fn((usage: unknown) => {
            trackerRecordUsageMock(usage);
            usageRecorded = true;
          }),
          recordRetryAfter: vi.fn(),
          snapshot: vi.fn(() => ({
            provider_requests: 1,
            ...(usageRecorded
              ? {
                  usage: {
                    input_tokens: 12,
                    output_tokens: 8,
                    total_tokens: 20,
                  },
                }
              : {}),
          })),
        },
      };
    });
    generateTextMock.mockImplementation((options: { model: { modelId: string } }) => {
      if (options.model.modelId === "z-ai/glm-5.2:free") {
        throw new Error("rate limited");
      }
      return Promise.resolve(
        validPayload(
          JSON.stringify({
            results: [
              { word: "QI", valid: true, reason: "Collins 2019" },
              { word: "ZA", valid: true, reason: "Collins 2019" },
            ],
          }),
        ),
      );
    });

    const response = await POST(judgeRequest());
    expect(response.status).toBe(200);
    const payload = await response.json();
    expect(payload.results).toEqual([
      { word: "QI", valid: true, reason: "Collins 2019" },
      { word: "ZA", valid: true, reason: "Collins 2019" },
    ]);
    expect(payload.model).toBe("nvidia/nemotron-3-super-120b-a12b:free");
    expect(payload.provider).toBe("openrouter");
    expect(payload.provider_requests_used).toBe(2);
    expect(payload.usage).toEqual({
      input_tokens: 12,
      output_tokens: 8,
      total_tokens: 20,
    });
    expect(trackerRecordUsageMock).toHaveBeenCalledWith({
      inputTokens: 12,
      outputTokens: 8,
      totalTokens: 20,
    });
    expect(order).toEqual([
      ["openrouter", "z-ai/glm-5.2:free"],
      ["openrouter", "nvidia/nemotron-3-super-120b-a12b:free"],
    ]);
    expect(generateTextMock).toHaveBeenCalledTimes(2);
    expect(generateTextMock).toHaveBeenCalledWith(
      expect.objectContaining({ maxRetries: 0 }),
    );
    vi.unstubAllGlobals();
  });

  it("advances after a no-endpoints AI provider 404 and returns rival 2's strict result", async () => {
    stubJudgeBackend();
    generateTextMock
      .mockRejectedValueOnce(
        Object.assign(
          new Error("No endpoints found for stealth/example:free"),
          { name: "AI_APICallError", statusCode: 404 },
        ),
      )
      .mockResolvedValueOnce(
        validPayload(
          JSON.stringify({
            results: [
              { word: "QI", valid: true, reason: "Collins 2019" },
              { word: "ZA", valid: true, reason: "Collins 2019" },
            ],
          }),
        ),
      );

    const response = await POST(judgeRequest());
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      provider: "openrouter",
      model: "nvidia/nemotron-3-super-120b-a12b:free",
      results: [
        { word: "QI", valid: true },
        { word: "ZA", valid: true },
      ],
    });
    expect(generateTextMock).toHaveBeenCalledTimes(2);
    expect(getLanguageRuntimeMock).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });

  it("honours a valid preference as attempt 1 via the shared queue", async () => {
    stubJudgeBackend();
    const seen: string[] = [];
    getLanguageRuntimeMock.mockImplementation(async (provider?: string, modelId?: string) => {
      seen.push(modelId ?? "");
      return {
        model: { provider: provider ?? "", modelId: modelId ?? "" },
        tracker: {
          noteProviderRequest: vi.fn(),
          recordUsage: trackerRecordUsageMock,
          recordRetryAfter: vi.fn(),
          snapshot: vi.fn(() => ({ provider_requests: 1 })),
        },
      };
    });
    generateTextMock.mockResolvedValue(
      validPayload(
        JSON.stringify({
          results: [
            { word: "QI", valid: false, reason: "not in Collins 2019" },
            { word: "ZA", valid: true },
          ],
        }),
      ),
    );

    const response = await POST(judgeRequest("google/gemma-4-31b-it:free"));
    expect(response.status).toBe(200);
    const payload = await response.json();
    expect(seen[0]).toBe("google/gemma-4-31b-it:free");
    expect(payload.results[0]).toMatchObject({ word: "QI", valid: false });
    expect(generateTextMock).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("advances past malformed output and never synthesizes invalid verdicts", async () => {
    stubJudgeBackend();
    const payloads = [
      "I cannot judge these words.", // model 1: no JSON
      JSON.stringify({ results: [{ word: "QI", valid: false }] }), // model 2: missing ZA
      JSON.stringify({
        results: [
          { word: "QI", valid: true },
          { word: "ZA", valid: true },
        ],
      }), // model 3: strict one-result-per-input payload
      JSON.stringify({
        results: [
          { word: "QI", valid: true },
          { word: "ZA", valid: true },
          { word: "EXTRA", valid: true }, // extra result must be rejected
        ],
      }),
    ];
    let call = 0;
    generateTextMock.mockImplementation(() => {
      const text = payloads[Math.min(call, payloads.length - 1)];
      call += 1;
      return Promise.resolve(validPayload(text));
    });

    const response = await POST(judgeRequest());
    expect(response.status).toBe(200);
    const payload = await response.json();
    expect(payload.results).toEqual([
      { word: "QI", valid: true },
      { word: "ZA", valid: true },
    ]);
    expect(generateTextMock).toHaveBeenCalledTimes(3);
    expect(getLanguageRuntimeMock).toHaveBeenCalledTimes(3);
    vi.unstubAllGlobals();
  });

  it("returns 503 after exhausting attempts without inventing results", async () => {
    stubJudgeBackend();
    generateTextMock.mockRejectedValue(new Error("all providers down"));

    const response = await POST(judgeRequest());
    expect(response.status).toBe(503);
    const payload = await response.json();
    expect(payload.error).toBeDefined();
    expect(payload.results).toBeUndefined();
    expect(generateTextMock).toHaveBeenCalledTimes(3);
    expect(getLanguageRuntimeMock).toHaveBeenCalledTimes(3);
    vi.unstubAllGlobals();
  });

  it("caps malformed-output retries at three models", async () => {
    stubJudgeBackend();
    generateTextMock.mockResolvedValue(validPayload("garbage output"));

    const response = await POST(judgeRequest());
    expect(response.status).toBe(503);
    expect(generateTextMock).toHaveBeenCalledTimes(3);
    vi.unstubAllGlobals();
  });

  it("fails closed with 503 when the catalog fetch fails or is empty", async () => {
    stubJudgeBackend({ catalogStatus: 500 });
    const failing = await POST(judgeRequest());
    expect(failing.status).toBe(503);
    expect(generateTextMock).not.toHaveBeenCalled();

    stubJudgeBackend({ catalog: [] });
    const empty = await POST(judgeRequest());
    expect(empty.status).toBe(503);
    expect(generateTextMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("rejects requests without usable words", async () => {
    stubJudgeBackend();
    const response = await POST(judgeRequest(undefined, { words: [] }));
    expect(response.status).toBe(400);
    expect(generateTextMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("starts a third lane with a sub-10s tail and sums bounded accounting", async () => {
    stubJudgeBackend();
    const nowValues = [
      0,
      0, 0,
      10_000, 10_000,
      29_995, 29_995,
    ];
    let nowIndex = 0;
    vi.spyOn(Date, "now").mockImplementation(
      () => nowValues[Math.min(nowIndex++, nowValues.length - 1)],
    );
    const timeoutValues: number[] = [];
    vi.spyOn(AbortSignal, "timeout").mockImplementation((milliseconds) => {
      timeoutValues.push(milliseconds);
      return new AbortController().signal;
    });
    let runtimeIndex = 0;
    getLanguageRuntimeMock.mockImplementation(async (provider?: string, modelId?: string) => {
      const index = runtimeIndex++;
      return {
        model: { provider: provider ?? "", modelId: modelId ?? "" },
        tracker: {
          noteProviderRequest: vi.fn(),
          recordUsage: trackerRecordUsageMock,
          recordRetryAfter: vi.fn(),
          snapshot: vi.fn(() => ({
            provider_requests: index + 1,
            ...(index === 1 ? { retry_after_seconds: 17 } : {}),
          })),
        },
      };
    });
    generateTextMock.mockImplementation(() => {
      if (generateTextMock.mock.calls.length < 3) {
        throw new Error("provider unavailable");
      }
      return Promise.resolve(
        validPayload(
          JSON.stringify({
            results: [
              { word: "QI", valid: true },
              { word: "ZA", valid: true },
            ],
          }),
        ),
      );
    });

    const response = await POST(judgeRequest());
    expect(response.status).toBe(200);
    expect(timeoutValues).toEqual([10_000, 10_000, 5]);
    expect(generateTextMock).toHaveBeenCalledTimes(3);
    expect(generateTextMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ maxRetries: 0 }),
    );
    expect(await response.json()).toMatchObject({
      provider_requests_used: 6,
      retry_after_seconds: 17,
      results: [
        { word: "QI", valid: true },
        { word: "ZA", valid: true },
      ],
    });
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("returns three-lane 503 accounting without synthesizing invalid verdicts", async () => {
    stubJudgeBackend();
    let runtimeIndex = 0;
    getLanguageRuntimeMock.mockImplementation(async (provider?: string, modelId?: string) => {
      const index = runtimeIndex++;
      return {
        model: { provider: provider ?? "", modelId: modelId ?? "" },
        tracker: {
          noteProviderRequest: vi.fn(),
          recordUsage: trackerRecordUsageMock,
          recordRetryAfter: vi.fn(),
          snapshot: vi.fn(() => ({
            provider_requests: 2,
            ...(index === 2 ? { retry_after_seconds: 86_400 } : {}),
          })),
        },
      };
    });
    generateTextMock.mockResolvedValue(validPayload("prose only"));

    const response = await POST(judgeRequest());
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual(
      expect.objectContaining({
        error: "AI judge failed",
        provider_requests_used: 6,
        retry_after_seconds: 86_400,
      }),
    );
    expect(generateTextMock).toHaveBeenCalledTimes(3);
    vi.unstubAllGlobals();
  });

  it("does not claim Collins when lexicon_id is slovak", async () => {
    stubJudgeBackend();
    generateTextMock.mockResolvedValue(
      validPayload(
        JSON.stringify({
          results: [
            { word: "QI", valid: true, reason: "shipped Slovak lexicon" },
            { word: "ZA", valid: true, reason: "shipped Slovak lexicon" },
          ],
        }),
      ),
    );

    const response = await POST(judgeRequest(undefined, { lexicon_id: "slovak" }));
    expect(response.status).toBe(200);
    const opts = generateTextMock.mock.calls[0][0] as {
      system: string;
      prompt: string;
    };
    expect(opts.system).not.toMatch(/Collins/i);
    expect(opts.system).toMatch(/shipped Slovak lexicon/i);
    expect(opts.prompt).toMatch(/Slovak/);
    expect(opts.prompt).not.toMatch(/Collins/i);
    vi.unstubAllGlobals();
  });

  it("returns 503 without fabricating invalids for a slovak lexicon request", async () => {
    stubJudgeBackend();
    generateTextMock.mockResolvedValue(validPayload("garbage output"));

    const response = await POST(judgeRequest(undefined, { lexicon_id: "slovak" }));
    expect(response.status).toBe(503);
    const payload = await response.json();
    expect(payload.error).toBeDefined();
    expect(payload.results).toBeUndefined();
    expect(generateTextMock).toHaveBeenCalledTimes(3);
    vi.unstubAllGlobals();
  });

const ME_PROFILE = {
  id: 1,
  username: "judge-user",
  email: "judge-user@example.test",
  preferred_ai_model_id: "",
  date_joined: "2026-01-01T00:00:00Z",
};

function jsonResponse(
  value: unknown,
  status = 200,
  extraHeaders?: Record<string, string>,
): Response {
  return new Response(typeof value === "string" ? value : JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json", ...extraHeaders },
  });
}

function stubJudgeBackend(options?: {
  meStatus?: number;
  meBody?: unknown;
  meReject?: boolean;
  meNonJson?: boolean;
  meRetryAfter?: string;
  catalog?: unknown;
  catalogStatus?: number;
}) {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/api/auth/me/")) {
      if (options?.meReject) {
        throw new Error("backend unreachable");
      }
      const status = options?.meStatus ?? 200;
      const extra = options?.meRetryAfter
        ? { "Retry-After": options.meRetryAfter }
        : undefined;
      if (options?.meNonJson) {
        return new Response("<html>upstream</html>", {
          status,
          headers: { "Content-Type": "text/html" },
        });
      }
      const body = options?.meBody !== undefined ? options.meBody : ME_PROFILE;
      return jsonResponse(body, status, extra);
    }
    if (url.includes("/api/catalog/models/")) {
      return jsonResponse(
        options?.catalog ?? NEWEST_CATALOG,
        options?.catalogStatus ?? 200,
      );
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function fetchUrls(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map(([url]) => String(url));
}

  describe("authentication and input caps", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns 401 and does not call generateText when Authorization is missing", async () => {
    const fetchMock = stubJudgeBackend();
    const response = await POST(judgeRequest(undefined, {}, null));
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "Authentication required" });
    expect(generateTextMock).not.toHaveBeenCalled();
    expect(getLanguageRuntimeMock).not.toHaveBeenCalled();
    expect(fetchUrls(fetchMock).some((url) => url.includes("/api/auth/me/"))).toBe(
      false,
    );
    expect(
      fetchUrls(fetchMock).some((url) => url.includes("/api/catalog/models/")),
    ).toBe(false);
  });

  it("returns 401 and does not call generateText when Authorization is malformed", async () => {
    const fetchMock = stubJudgeBackend();
    const response = await POST(judgeRequest(undefined, {}, "Token not-a-bearer"));
    expect(response.status).toBe(401);
    expect(generateTextMock).not.toHaveBeenCalled();
    expect(getLanguageRuntimeMock).not.toHaveBeenCalled();
    expect(fetchUrls(fetchMock).some((url) => url.includes("/api/auth/me/"))).toBe(
      false,
    );
  });

  it("returns 401 and does not call generateText when Django verification is 401", async () => {
    const fetchMock = stubJudgeBackend({
      meStatus: 401,
      meBody: { detail: "Authentication credentials were not provided." },
    });
    const response = await POST(judgeRequest());
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "Authentication required" });
    expect(generateTextMock).not.toHaveBeenCalled();
    expect(getLanguageRuntimeMock).not.toHaveBeenCalled();
    const urls = fetchUrls(fetchMock);
    expect(urls.some((url) => url.includes("/api/auth/me/"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/catalog/models/"))).toBe(false);
  });

  it("returns 429 and does not call generateText when Django verification is 429", async () => {
    const fetchMock = stubJudgeBackend({
      meStatus: 429,
      meBody: { detail: "Request was throttled." },
      meRetryAfter: "12",
    });
    const response = await POST(judgeRequest());
    expect(response.status).toBe(429);
    expect(response.headers.get("Retry-After")).toBe("12");
    expect(await response.json()).toEqual({ error: "Too many requests" });
    expect(generateTextMock).not.toHaveBeenCalled();
    expect(getLanguageRuntimeMock).not.toHaveBeenCalled();
    expect(
      fetchUrls(fetchMock).some((url) => url.includes("/api/catalog/models/")),
    ).toBe(false);
  });

  it("returns 503 and does not call generateText when Django verification rejects", async () => {
    stubJudgeBackend({ meReject: true });
    const response = await POST(judgeRequest());
    expect(response.status).toBe(503);
    expect(generateTextMock).not.toHaveBeenCalled();
    expect(getLanguageRuntimeMock).not.toHaveBeenCalled();
  });

  it("returns 503 and does not call generateText when Django verification body is unexpected", async () => {
    const fetchMock = stubJudgeBackend({ meBody: NEWEST_CATALOG });
    const response = await POST(judgeRequest());
    expect(response.status).toBe(503);
    expect(generateTextMock).not.toHaveBeenCalled();
    expect(getLanguageRuntimeMock).not.toHaveBeenCalled();
    expect(
      fetchUrls(fetchMock).some((url) => url.includes("/api/catalog/models/")),
    ).toBe(false);
  });

  it("rejects an oversize words array before getLanguageRuntime and generateText", async () => {
    const fetchMock = stubJudgeBackend();
    const words = Array.from({ length: MAX_JUDGE_WORDS + 1 }, (_, index) => `W${index}`);
    const response = await POST(judgeRequest(undefined, { words }));
    expect(response.status).toBe(400);
    expect(generateTextMock).not.toHaveBeenCalled();
    expect(getLanguageRuntimeMock).not.toHaveBeenCalled();
    const urls = fetchUrls(fetchMock);
    expect(urls.some((url) => url.includes("/api/auth/me/"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/catalog/models/"))).toBe(false);
  });

  it("rejects an over-long word before getLanguageRuntime and generateText", async () => {
    const fetchMock = stubJudgeBackend();
    const response = await POST(
      judgeRequest(undefined, { words: ["A".repeat(MAX_JUDGE_WORD_LENGTH + 1)] }),
    );
    expect(response.status).toBe(400);
    expect(generateTextMock).not.toHaveBeenCalled();
    expect(getLanguageRuntimeMock).not.toHaveBeenCalled();
    const urls = fetchUrls(fetchMock);
    expect(urls.some((url) => url.includes("/api/auth/me/"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/catalog/models/"))).toBe(false);
  });

  it("calls Django verification before catalog fetch and generateText on the happy path", async () => {
    const fetchMock = stubJudgeBackend();
    generateTextMock.mockResolvedValue(
      validPayload(
        JSON.stringify({
          results: [
            { word: "QI", valid: true, reason: "Collins 2019" },
            { word: "ZA", valid: true, reason: "Collins 2019" },
          ],
        }),
      ),
    );
    const response = await POST(judgeRequest());
    expect(response.status).toBe(200);
    const payload = await response.json();
    expect(payload.results).toEqual([
      { word: "QI", valid: true, reason: "Collins 2019" },
      { word: "ZA", valid: true, reason: "Collins 2019" },
    ]);
    expect(payload.results.some((row: { valid: boolean }) => row.valid === false)).toBe(
      false,
    );
    const urls = fetchUrls(fetchMock);
    const meIndex = urls.findIndex((url) => url.includes("/api/auth/me/"));
    const catalogIndex = urls.findIndex((url) => url.includes("/api/catalog/models/"));
    expect(meIndex).toBeGreaterThanOrEqual(0);
    expect(catalogIndex).toBeGreaterThan(meIndex);
    expect(generateTextMock).toHaveBeenCalled();
  });
  });
});
