import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ProviderRuntimeError,
  createProviderRequestTracker,
  createTrackedProviderFetch,
  requireServerCredential,
} from "./openai-compatible";

function response(status = 200, retryAfter?: string): Response {
  return new Response("{}", {
    status,
    headers: retryAfter ? { "Retry-After": retryAfter } : undefined,
  });
}

function namedToolBody(tools: string[]): string {
  return JSON.stringify({
    model: "@cf/zai-org/glm-4.7-flash",
    messages: [{ role: "user", content: "ping" }],
    tools: tools.map((name) => ({
      type: "function",
      function: { name, parameters: { type: "object" } },
    })),
    tool_choice: {
      type: "function",
      function: { name: "validateMove" },
    },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ProviderRequestTracker", () => {
  it("counts failed HTTP responses and keeps only bounded numeric telemetry", async () => {
    const tracker = createProviderRequestTracker();
    vi.stubGlobal("fetch", vi.fn(async () => response(429, "999999")));
    const trackedFetch = createTrackedProviderFetch(tracker);

    const result = await trackedFetch("https://provider.invalid/v1/chat", {
      method: "POST",
      headers: { Authorization: "Bearer test-secret" },
      body: "secret prompt",
    });

    expect(result.status).toBe(429);
    expect(tracker.snapshot()).toEqual({
      provider_requests: 1,
      retry_after_seconds: 86_400,
    });
    expect(JSON.stringify(tracker.snapshot())).not.toContain("secret");
    expect(JSON.stringify(tracker.snapshot())).not.toContain("provider.invalid");
  });

  it("normalizes and accumulates token usage without retaining raw metadata", () => {
    const tracker = createProviderRequestTracker();
    tracker.recordUsage({
      inputTokens: { total: 12, cacheRead: 4 },
      outputTokens: { total: 8, reasoning: 3 },
      totalTokens: 20,
      raw: { secret: "never-store-this" },
    });
    tracker.recordUsage({ inputTokens: 3, outputTokens: 2, totalTokens: 5 });
    expect(tracker.snapshot()).toEqual({
      provider_requests: 0,
      usage: { input_tokens: 15, output_tokens: 10, total_tokens: 25 },
    });
    expect(JSON.stringify(tracker.snapshot())).not.toContain("never-store-this");
  });

  it("parses Retry-After dates and ignores malformed values", () => {
    const tracker = createProviderRequestTracker();
    const now = Date.parse("2026-08-26T10:00:00Z");
    tracker.recordRetryAfter("not-a-date", now);
    tracker.recordRetryAfter("Wed, 26 Aug 2026 10:00:12 GMT", now);
    expect(tracker.snapshot().retry_after_seconds).toBe(12);
  });
});

describe("Cloudflare named tool translation", () => {
  it("rewrites only the single forced validateMove tool and preserves payload", async () => {
    const tracker = createProviderRequestTracker();
    const fetchMock = vi.fn<
      (input: string | URL | Request, init?: RequestInit) => Promise<Response>
    >(async () => response());
    vi.stubGlobal("fetch", fetchMock);
    const trackedFetch = createTrackedProviderFetch(tracker, {
      cloudflareNamedToolChoice: true,
    });

    await trackedFetch("https://cloudflare.invalid/chat", {
      method: "POST",
      body: namedToolBody(["validateMove"]),
    });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const payload = JSON.parse(String(init.body));
    expect(payload.tool_choice).toBe("required");
    expect(payload.tools[0].function.name).toBe("validateMove");
    expect(payload.messages).toEqual([{ role: "user", content: "ping" }]);
    expect(tracker.snapshot().provider_requests).toBe(1);
  });

  it("fails closed before network for named zero/multi/different tools", async () => {
    const fetchMock = vi.fn<
      (input: string | URL | Request, init?: RequestInit) => Promise<Response>
    >(async () => response());
    vi.stubGlobal("fetch", fetchMock);
    for (const tools of [[], ["validateMove", "finishMove"], ["finishMove"]]) {
      const tracker = createProviderRequestTracker();
      const trackedFetch = createTrackedProviderFetch(tracker, {
        cloudflareNamedToolChoice: true,
      });
      await expect(
        trackedFetch("https://cloudflare.invalid/chat", {
          method: "POST",
          body: namedToolBody(tools),
        }),
      ).rejects.toMatchObject({ code: "provider_unavailable" });
      expect(tracker.snapshot().provider_requests).toBe(0);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not rewrite requests without a named choice", async () => {
    const tracker = createProviderRequestTracker();
    const fetchMock = vi.fn<
      (input: string | URL | Request, init?: RequestInit) => Promise<Response>
    >(async () => response());
    vi.stubGlobal("fetch", fetchMock);
    const trackedFetch = createTrackedProviderFetch(tracker, {
      cloudflareNamedToolChoice: true,
    });
    const body = JSON.stringify({ tool_choice: "auto", tools: [] });
    await trackedFetch("https://cloudflare.invalid/chat", {
      method: "POST",
      body,
    });
    expect((fetchMock.mock.calls[0][1] as RequestInit).body).toBe(body);
  });
});

describe("createTrackedProviderFetch logging", () => {
  it("logs a non-2xx response once without changing return, tracker, or Retry-After", async () => {
    const writeSpy = vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const tracker = createProviderRequestTracker();
    vi.stubGlobal("fetch", vi.fn(async () => response(429, "12")));
    const trackedFetch = createTrackedProviderFetch(tracker, { provider: "openrouter" });
    const result = await trackedFetch("https://provider.invalid/v1/chat", {
      method: "POST",
      headers: { Authorization: "Bearer test-secret" },
      body: "secret prompt",
    });
    expect(result.status).toBe(429);
    expect(tracker.snapshot()).toEqual({
      provider_requests: 1,
      retry_after_seconds: 12,
    });
    expect(writeSpy).toHaveBeenCalledTimes(1);
    writeSpy.mockRestore();
  });

  it("logs a thrown transport error once and still propagates it", async () => {
    const writeSpy = vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const tracker = createProviderRequestTracker();
    const transport = new TypeError("synthetic transport failure");
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw transport;
    }));
    const trackedFetch = createTrackedProviderFetch(tracker, { provider: "groq" });
    await expect(
      trackedFetch("https://provider.invalid/v1/chat"),
    ).rejects.toBe(transport);
    expect(tracker.snapshot().provider_requests).toBe(1);
    expect(writeSpy).toHaveBeenCalledTimes(1);
    writeSpy.mockRestore();
  });
});

describe("credential validation", () => {
  it("rejects blank and documented placeholders with a sanitized error", () => {
    for (const value of [undefined, "", "   ", "your-api-key", "replace-me"]) {
      let caught: unknown;
      try {
        requireServerCredential(value);
      } catch (error) {
        caught = error;
      }
      expect(caught).toBeInstanceOf(ProviderRuntimeError);
      expect(caught).toMatchObject({ code: "provider_auth_failed" });
      const serialized = String(caught);
      if (value?.trim()) expect(serialized).not.toContain(value);
      expect(serialized).not.toMatch(/[A-Z_]+=/);
    }
  });

  it("constructs a sanitized provider rate-limit runtime error", () => {
    const error = new ProviderRuntimeError("provider_rate_limited");
    expect(error).toMatchObject({ code: "provider_rate_limited" });
    expect(String(error)).toBe(
      "ProviderRuntimeError: This free rival is rate limited. Switch to another free rival or retry later.",
    );
    expect(String(error)).not.toMatch(/[A-Z_]+=/);
  });
});
