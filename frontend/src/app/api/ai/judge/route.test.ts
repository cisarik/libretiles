import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { generateTextMock, getLanguageModelMock, findCuratedPairMock } = vi.hoisted(
  () => ({
    generateTextMock: vi.fn(),
    getLanguageModelMock: vi.fn(() => ({ provider: "test", modelId: "test" })),
    findCuratedPairMock: vi.fn(() => ({
      provider: "nvidia-nim",
      modelId: "nvidia/nemotron-3-super-120b-a12b",
    })),
  }),
);

vi.mock("ai", () => ({ generateText: generateTextMock }));

vi.mock("@/lib/ai-runtimes", () => ({
  findCuratedPair: findCuratedPairMock,
  getLanguageModel: getLanguageModelMock,
}));

import { POST } from "./route";

describe("POST /api/ai/judge", () => {
  beforeEach(() => {
    generateTextMock.mockReset();
    getLanguageModelMock.mockClear();
    findCuratedPairMock.mockClear();
  });

  it("dispatches one curated rival exactly once with no fallback loop", async () => {
    generateTextMock.mockResolvedValue({
      text: JSON.stringify({
        results: [{ word: "QI", valid: true, reason: "Collins 2019" }],
      }),
      usage: { inputTokens: 12, outputTokens: 8, totalTokens: 20 },
    });
    const request = new NextRequest("http://localhost/api/ai/judge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        words: ["QI"],
        model_id: "nvidia/nemotron-3-super-120b-a12b",
      }),
    });

    const response = await POST(request);
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      results: [{ word: "QI", valid: true }],
    });
    expect(findCuratedPairMock).toHaveBeenCalledTimes(1);
    expect(getLanguageModelMock).toHaveBeenCalledTimes(1);
    expect(getLanguageModelMock).toHaveBeenCalledWith(
      "nvidia-nim",
      "nvidia/nemotron-3-super-120b-a12b",
    );
    expect(generateTextMock).toHaveBeenCalledTimes(1);
  });
});
