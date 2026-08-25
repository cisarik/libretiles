import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { generateTextMock, getLanguageModelMock } = vi.hoisted(() => ({
  generateTextMock: vi.fn(),
  getLanguageModelMock: vi.fn(
    (provider?: string, modelId?: string) => ({
      provider: provider ?? "",
      modelId: modelId ?? "",
    }),
  ),
}));

vi.mock("ai", () => ({ generateText: generateTextMock }));

vi.mock("@/lib/ai-runtimes", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ai-runtimes")>();
  return {
    ...actual,
    getLanguageModel: getLanguageModelMock,
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
    getLanguageModelMock.mockClear();
  });

  it("walks the newest-first queue when the first model fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
    const order: Array<[string, string]> = [];
    getLanguageModelMock.mockImplementation((provider?: string, modelId?: string) => {
      order.push([provider ?? "", modelId ?? ""]);
      return { provider: provider ?? "", modelId: modelId ?? "" };
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

  it("honours a valid preference as attempt 1 via the shared queue", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
    const seen: string[] = [];
    getLanguageModelMock.mockImplementation((provider?: string, modelId?: string) => {
      seen.push(modelId ?? "");
      return { provider: provider ?? "", modelId: modelId ?? "" };
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
    expect(getLanguageModelMock).toHaveBeenCalledTimes(3);
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
    expect(generateTextMock).toHaveBeenCalledTimes(3);
    expect(getLanguageModelMock).toHaveBeenCalledTimes(3);
    vi.unstubAllGlobals();
  });

  it("caps malformed-output retries at three models", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(NEWEST_CATALOG), { status: 200 })),
    );
    generateTextMock.mockResolvedValue(validPayload("garbage output"));

    const response = await POST(judgeRequest());
    expect(response.status).toBe(503);
    expect(generateTextMock).toHaveBeenCalledTimes(3);
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
});
