import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET as getModels } from "./models/route";
import { GET as getPrompts } from "./prompts/route";

const UPSTREAM_BODY = "DJANGO_SECRET_LEAK_TOKEN_f3c91a";
const UPSTREAM_STATUS_TEXT = "Internal Server Error FROM_DJANGO_f3c91a";
const SUCCESS_PAYLOAD = [
  { provider: "openrouter", model_id: "google/gemma-4-31b-it:free" },
];

type RouteCase = {
  name: "models" | "prompts";
  handler: typeof getModels;
  pathSuffix: string;
};

const ROUTES: RouteCase[] = [
  { name: "models", handler: getModels, pathSuffix: "/api/catalog/models/" },
  { name: "prompts", handler: getPrompts, pathSuffix: "/api/catalog/prompts/" },
];

function asInit(call: unknown[] | undefined): Record<string, unknown> {
  const init = call?.[1];
  expect(init).toBeTypeOf("object");
  expect(init).not.toBeNull();
  return init as Record<string, unknown>;
}

describe("catalog proxy routes", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  describe.each(ROUTES)("$name", ({ handler, pathSuffix }) => {
    it("AC-PROXY-UPSTREAM-FAIL: upstream 500 becomes 500 catalog_unavailable, not []/200", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(UPSTREAM_BODY, {
          status: 500,
          statusText: UPSTREAM_STATUS_TEXT,
        }),
      );

      const response = await handler();
      const body = await response.json();

      expect(response.status).toBe(500);
      expect(body).toEqual({
        error: "catalog_unavailable",
        upstream_status: 500,
      });
      expect(body).not.toEqual([]);
    });

    it("AC-PROXY-UNREACHABLE: a rejected fetch becomes 502 catalog_unreachable, not []/200", async () => {
      vi.mocked(globalThis.fetch).mockRejectedValue(
        new Error(`ECONNREFUSED ${UPSTREAM_BODY}`),
      );

      const response = await handler();
      const body = await response.json();

      expect(response.status).toBe(502);
      expect(body).toEqual({ error: "catalog_unreachable" });
      expect(body).not.toEqual([]);
    });

    it("AC-PROXY-SUCCESS: a stubbed 200 JSON array is returned unchanged", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify(SUCCESS_PAYLOAD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

      const response = await handler();
      const text = await response.text();

      expect(response.status).toBe(200);
      expect(text).toBe(JSON.stringify(SUCCESS_PAYLOAD));
    });

    it("AC-PROXY-NO-LEAK: neither error body contains Django status text or body", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(UPSTREAM_BODY, {
          status: 500,
          statusText: UPSTREAM_STATUS_TEXT,
          headers: { "X-Django-Debug": UPSTREAM_BODY },
        }),
      );

      const upstreamFail = await handler();
      const upstreamText = await upstreamFail.text();
      expect(upstreamText).not.toContain(UPSTREAM_BODY);
      expect(upstreamText).not.toContain(UPSTREAM_STATUS_TEXT);
      expect(upstreamText).not.toContain("FROM_DJANGO");

      vi.mocked(globalThis.fetch).mockRejectedValue(
        new Error(`ECONNREFUSED ${UPSTREAM_BODY} ${UPSTREAM_STATUS_TEXT}`),
      );
      const unreachable = await handler();
      const unreachableText = await unreachable.text();
      expect(unreachableText).not.toContain(UPSTREAM_BODY);
      expect(unreachableText).not.toContain(UPSTREAM_STATUS_TEXT);
      expect(unreachableText).not.toContain("FROM_DJANGO");
    });

    it("AC-PROXY-NO-STORE: fetch uses cache no-store and does not pass revalidate", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify(SUCCESS_PAYLOAD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

      await handler();

      expect(globalThis.fetch).toHaveBeenCalledTimes(1);
      const call = vi.mocked(globalThis.fetch).mock.calls[0];
      expect(String(call[0])).toMatch(new RegExp(`${pathSuffix}$`));
      const init = asInit(call);
      expect(init.cache).toBe("no-store");
      expect(init).not.toHaveProperty("next");
      expect(JSON.stringify(init)).not.toContain("revalidate");
    });
  });
});
