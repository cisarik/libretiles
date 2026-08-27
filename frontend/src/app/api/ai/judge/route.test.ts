import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

function judgeRequest(modelId?: string): NextRequest {
  return new NextRequest("http://localhost/api/ai/judge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      modelId === undefined
        ? { words: ["QI", "ZA"] }
        : { words: ["QI", "ZA"], model_id: modelId },
    ),
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
    generateTextMock.mockRejectedValue(new Error("all providers down"));

    const response = await POST(judgeRequest());
    expect(response.status).toBe(503);
    const payload = await response.json();
    expect(payload.error).toBeDefined();
    expect(payload.results).toBeUndefined();
    expect(generateTextMock).toHaveBeenCalledTimes(5);
    expect(getLanguageRuntimeMock).toHaveBeenCalledTimes(5);
    vi.unstubAllGlobals();
  });

  it("caps malformed-output retries at five models", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
    generateTextMock.mockResolvedValue(validPayload("garbage output"));

    const response = await POST(judgeRequest());
    expect(response.status).toBe(503);
    expect(generateTextMock).toHaveBeenCalledTimes(5);
    vi.unstubAllGlobals();
  });

  it("fails closed with 503 when the catalog fetch fails or is empty", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("nope", { status: 500 })),
    );
    const failing = await POST(judgeRequest());
    expect(failing.status).toBe(503);
    expect(generateTextMock).not.toHaveBeenCalled();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })),
    );
    const empty = await POST(judgeRequest());
    expect(empty.status).toBe(503);
    expect(generateTextMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("rejects requests without usable words", async () => {
    const request = new NextRequest("http://localhost/api/ai/judge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ words: [] }),
    });
    const response = await POST(request);
    expect(response.status).toBe(400);
    expect(generateTextMock).not.toHaveBeenCalled();
  });

  it("starts a fifth lane with a sub-10s tail and sums bounded accounting", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
    const nowValues = [
      0,
      0, 0,
      10_000, 10_000,
      20_000, 20_000,
      30_000, 30_000,
      49_995, 49_995,
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
      if (generateTextMock.mock.calls.length < 5) {
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
    expect(timeoutValues).toEqual([10_000, 10_000, 10_000, 10_000, 5]);
    expect(generateTextMock).toHaveBeenCalledTimes(5);
    expect(generateTextMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ maxRetries: 0 }),
    );
    expect(await response.json()).toMatchObject({
      provider_requests_used: 15,
      retry_after_seconds: 17,
      results: [
        { word: "QI", valid: true },
        { word: "ZA", valid: true },
      ],
    });
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("returns five-lane 503 accounting without synthesizing invalid verdicts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
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
            ...(index === 4 ? { retry_after_seconds: 86_400 } : {}),
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
        provider_requests_used: 10,
        retry_after_seconds: 86_400,
      }),
    );
    expect(generateTextMock).toHaveBeenCalledTimes(5);
    vi.unstubAllGlobals();
  });
});
