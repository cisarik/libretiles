import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { currentAiMoveBackendTransport } from "@/lib/ai-move-execution";

const { executeAiMoveMock } = vi.hoisted(() => ({
  executeAiMoveMock: vi.fn(),
}));

vi.mock("@/app/api/ai/move/route", () => ({
  POST: executeAiMoveMock,
}));

import { POST } from "./route";

const USER_GAME_ID = "0f8f7f6f-5e5d-4c4b-9a8a-7b6c5d4e3f21";
const OTHER_GAME_ID = "11111111-2222-4333-8444-555566667777";

function contextFor(id: string) {
  return { params: Promise.resolve({ id }) } as RouteContext<
    "/api/admin/simulate/[id]/turn"
  >;
}

function turnRequest(
  id: string,
  body: unknown = { expected_move_count: 0 },
  headers: Record<string, string> = {},
): NextRequest {
  return new NextRequest(`http://localhost/api/admin/simulate/${id}/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubBackend(
  handler: (url: string, init?: RequestInit) => Response | Promise<Response>,
) {
  const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) =>
    handler(String(url), init),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// The LLM mock stands in for the real /api/ai/move POST but still reads the
// route-installed AsyncLocalStorage transport, so every LLM test proves the
// binding instead of mocking away the isolation mechanism under test.
executeAiMoveMock.mockImplementation(async () => {
  const transport = currentAiMoveBackendTransport();
  let actionFailed = false;
  if (transport) {
    try {
      await transport("/api/game/any/ai-context/", {});
    } catch {
      actionFailed = true;
    }
  }
  if (actionFailed) {
    return new Response(
      'data: {"type":"error","error":"The AI turn could not be completed."}\n\n',
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    );
  }
  return new Response('data: {"type":"done","action":"place","ok":true}\n\n', {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
});

const LLM_CLAIM = {
  kind: "llm",
  lease_id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
  model_id: "nvidia/nemotron-3-super-120b-a12b",
  timeout: 30,
  max_steps: 10,
};

describe("admin simulation turn route", () => {
  beforeEach(() => {
    executeAiMoveMock.mockClear();
  });

  afterEach(() => vi.unstubAllGlobals());

  it("rejects missing or malformed authentication before claiming a turn", async () => {
    const badHeaders: Array<Record<string, string> | undefined> = [
      undefined,
      { Authorization: "Bearer" },
      { Authorization: "Bearer " },
      { Authorization: "Basic dXNwZXI6" },
      { Authorization: "Bearer a b" },
    ];
    for (const headers of badHeaders) {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      const response = await POST(
        turnRequest(USER_GAME_ID, { expected_move_count: 0 }, headers),
        contextFor(USER_GAME_ID),
      );
      expect(response.status).toBe(401);
      expect(fetchMock).not.toHaveBeenCalled();
      expect(executeAiMoveMock).not.toHaveBeenCalled();
      vi.unstubAllGlobals();
    }
  });

  it("rejects an invalid route UUID with 404 before any backend call", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const response = await POST(
      turnRequest("game-1", { expected_move_count: 0 }, {
        Authorization: "Bearer staff-token",
      }),
      contextFor("game-1"),
    );
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ detail: "Not found." });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(executeAiMoveMock).not.toHaveBeenCalled();
  });

  it("rejects an invalid expected_move_count with 400", async () => {
    for (const body of [
      {},
      { expected_move_count: -1 },
      { expected_move_count: 1.5 },
      { expected_move_count: "3" },
      { expected_move_count: true },
    ]) {
      const fetchMock = stubBackend(async (url) => {
        throw new Error(`unexpected ${url}`);
      });
      const response = await POST(
        turnRequest(USER_GAME_ID, body, { Authorization: "Bearer staff-token" }),
        contextFor(USER_GAME_ID),
      );
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
      expect(executeAiMoveMock).not.toHaveBeenCalled();
      vi.unstubAllGlobals();
    }
  });

  it("short-circuits CPU turns without invoking a provider", async () => {
    stubBackend(async (url) => {
      if (String(url).endsWith("/step/")) {
        return jsonResponse(
          {
            kind: "cpu",
            state: {
              simulation_schema_version: 1,
              game_id: USER_GAME_ID,
            },
          },
          200,
        );
      }
      throw new Error(`unexpected ${url}`);
    });
    const response = await POST(
      turnRequest(USER_GAME_ID, { expected_move_count: 0 }, {
        Authorization: "Bearer staff-token",
      }),
      contextFor(USER_GAME_ID),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(await response.text()).toContain('"turn_provider_requests_used":0');
    expect(executeAiMoveMock).not.toHaveBeenCalled();
  });

  it("maps claim 4xx statuses to controlled errors without an AI POST", async () => {
    const cases: Array<[number, string]> = [
      [400, "The simulation request was invalid."],
      [401, "Authentication credentials were invalid or expired."],
      [403, "Staff access is required."],
      [404, "Not found."],
      [409, "The simulation state changed. Reload and retry."],
      [429, "Too many simulation requests. Retry later."],
    ];
    for (const [status, detail] of cases) {
      const fetchMock = stubBackend(async (url) => {
        if (String(url).endsWith("/step/")) {
          return jsonResponse({ detail: "raw backend detail", nested: { x: 1 } }, status);
        }
        throw new Error(`unexpected ${url}`);
      });
      const response = await POST(
        turnRequest(USER_GAME_ID, { expected_move_count: 0 }, {
          Authorization: "Bearer staff-token",
        }),
        contextFor(USER_GAME_ID),
      );
      expect(response.status).toBe(status);
      const body = await response.json();
      expect(body.detail).toBe(detail);
      if (status === 409) {
        expect(body.code).toBe("state_conflict");
      } else {
        expect(body).toEqual({ detail });
      }
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes("/action/")),
      ).toBe(false);
      expect(executeAiMoveMock).not.toHaveBeenCalled();
      vi.unstubAllGlobals();
    }
  });

  it("treats a claim 403 with a success-shaped LLM body as 403", async () => {
    const fetchMock = stubBackend(async (url) => {
      if (String(url).endsWith("/step/")) {
        return jsonResponse({ ...LLM_CLAIM, ok: true }, 403);
      }
      throw new Error(`unexpected ${url}`);
    });
    const response = await POST(
      turnRequest(USER_GAME_ID, { expected_move_count: 0 }, {
        Authorization: "Bearer staff-token",
      }),
      contextFor(USER_GAME_ID),
    );
    expect(response.status).toBe(403);
    expect((await response.json()).detail).toBe("Staff access is required.");
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/action/")),
    ).toBe(false);
    expect(executeAiMoveMock).not.toHaveBeenCalled();
  });

  it("maps backend 5xx and thrown transports to a controlled 503", async () => {
    stubBackend(async (url) => {
      if (String(url).endsWith("/step/")) {
        return jsonResponse(
          { detail: "boom", api_key: "sk-leak", authorization: "Bearer z", nested: { secret: "inner-leak" } },
          500,
        );
      }
      throw new Error(`unexpected ${url}`);
    });
    const response = await POST(
      turnRequest(USER_GAME_ID, { expected_move_count: 0 }, {
        Authorization: "Bearer staff-token",
      }),
      contextFor(USER_GAME_ID),
    );
    expect(response.status).toBe(503);
    const text = await response.text();
    expect(text).toContain("The simulation backend is unavailable.");
    for (const fragment of ["sk-leak", "inner-leak", "boom", "Bearer z"]) {
      expect(text).not.toContain(fragment);
    }
    expect(executeAiMoveMock).not.toHaveBeenCalled();
  });

  it("returns 503 on a transport throw and 502 on non-JSON success", async () => {
    stubBackend(async (url) => {
      if (String(url).endsWith("/step/")) throw new Error("backend unreachable");
      throw new Error(`unexpected ${url}`);
    });
    const thrown = await POST(
      turnRequest(USER_GAME_ID, { expected_move_count: 0 }, {
        Authorization: "Bearer staff-token",
      }),
      contextFor(USER_GAME_ID),
    );
    expect(thrown.status).toBe(503);
    expect((await thrown.json()).detail).toBe("The simulation backend is unavailable.");

    vi.unstubAllGlobals();
    stubBackend(async (url) => {
      if (String(url).endsWith("/step/")) return new Response("<html>nope</html>", { status: 200 });
      throw new Error(`unexpected ${url}`);
    });
    const html = await POST(
      turnRequest(USER_GAME_ID, { expected_move_count: 0 }, {
        Authorization: "Bearer staff-token",
      }),
      contextFor(USER_GAME_ID),
    );
    expect(html.status).toBe(502);
    expect((await html.json()).detail).toBe("The simulation backend returned an invalid response.");
    expect(executeAiMoveMock).not.toHaveBeenCalled();
  });

  it("rejects invalid CPU and LLM success shapes with 502", async () => {
    const badClaims = [
      { kind: "cpu", state: { simulation_schema_version: 1 } },
      { kind: "cpu", state: { game_id: USER_GAME_ID } },
      { kind: "cpu", state: [] },
      { kind: "llm" },
      { kind: "llm", lease_id: 5, model_id: "model-a" },
      { kind: "weird" },
    ];
    for (const claim of badClaims) {
      stubBackend(async (url) => {
        if (String(url).endsWith("/step/")) return jsonResponse(claim, 200);
        throw new Error(`unexpected ${url}`);
      });
      const response = await POST(
        turnRequest(USER_GAME_ID, { expected_move_count: 0 }, {
          Authorization: "Bearer staff-token",
        }),
        contextFor(USER_GAME_ID),
      );
      expect(response.status).toBe(502);
      expect((await response.json()).detail).toBe(
        "The simulation backend returned an invalid response.",
      );
      expect(executeAiMoveMock).not.toHaveBeenCalled();
      vi.unstubAllGlobals();
    }
  });

  it("delegates an LLM turn exactly once with claim and route arguments only", async () => {
    stubBackend(async (url) => {
      const u = String(url);
      if (u.endsWith("/step/")) return jsonResponse(LLM_CLAIM, 200);
      if (u.includes("/action/")) return jsonResponse({ ok: true }, 200);
      throw new Error(`unexpected ${u}`);
    });
    const response = await POST(
      turnRequest(USER_GAME_ID, { expected_move_count: 3 }, {
        Authorization: "Bearer staff-token",
      }),
      contextFor(USER_GAME_ID),
    );
    expect(response.status).toBe(200);
    expect(executeAiMoveMock).toHaveBeenCalledTimes(1);
    const delegatedRequest = executeAiMoveMock.mock.calls[0][0] as NextRequest;
    const delegatedBody = await delegatedRequest.json();
    expect(delegatedBody).toEqual({
      game_id: USER_GAME_ID,
      token: "staff-token",
      model_id: LLM_CLAIM.model_id,
      runtime_model_id: LLM_CLAIM.model_id,
      timeout: LLM_CLAIM.timeout,
      max_steps: LLM_CLAIM.max_steps,
    });
    expect(response.headers.get("Cache-Control")).toBe(
      "private, no-store, no-transform",
    );
    expect(response.headers.get("Vary")).toContain("Authorization");
  });

  it("never forwards extra body token, lease, or runtime fields", async () => {
    stubBackend(async (url) => {
      const u = String(url);
      if (u.endsWith("/step/")) return jsonResponse(LLM_CLAIM, 200);
      if (u.includes("/action/")) return jsonResponse({ ok: true }, 200);
      throw new Error(`unexpected ${u}`);
    });
    const response = await POST(
      turnRequest(
        USER_GAME_ID,
        {
          expected_move_count: 0,
          lease_id: "stale-lease",
          api_key: "sk-leak",
          runtime_url: "http://127.0.0.1:9",
          token: "attacker-token",
          runtime: { mode: "fake" },
        },
        { Authorization: "Bearer staff-token" },
      ),
      contextFor(USER_GAME_ID),
    );
    expect(response.status).toBe(200);
    expect(executeAiMoveMock).toHaveBeenCalledTimes(1);
    const delegatedBody = await (executeAiMoveMock.mock.calls[0][0] as NextRequest).json();
    expect(delegatedBody).toEqual({
      game_id: USER_GAME_ID,
      token: "staff-token",
      model_id: LLM_CLAIM.model_id,
      runtime_model_id: LLM_CLAIM.model_id,
      timeout: LLM_CLAIM.timeout,
      max_steps: LLM_CLAIM.max_steps,
    });
    const text = await response.text();
    expect(text).not.toContain("sk-leak");
    expect(text).not.toContain("attacker-token");
  });

  it("treats non-success action HTTP as failure even with ok:true", async () => {
    stubBackend(async (url) => {
      const u = String(url);
      if (u.endsWith("/step/")) return jsonResponse(LLM_CLAIM, 200);
      if (u.includes("/action/")) {
        return jsonResponse({ ok: true, lease_id: "stale" }, 409);
      }
      throw new Error(`unexpected ${u}`);
    });
    const response = await POST(
      turnRequest(USER_GAME_ID, { expected_move_count: 0 }, {
        Authorization: "Bearer staff-token",
      }),
      contextFor(USER_GAME_ID),
    );
    const text = await response.text();
    expect(text).toContain('"type":"error"');
    expect(text).not.toContain('"ok":true');
    expect(text).not.toContain("stale");
  });

  it("keeps distinct AsyncLocalStorage bindings for concurrent turns", async () => {
    const claimA = { ...LLM_CLAIM, lease_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", model_id: "model-a" };
    const claimB = { ...LLM_CLAIM, lease_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", model_id: "model-b" };
    const actionCalls: Array<{ url: string; body: Record<string, unknown> }> = [];
    stubBackend(async (url, init) => {
      const u = String(url);
      if (u.includes(`/simulate/${USER_GAME_ID}/step/`)) return jsonResponse(claimA, 200);
      if (u.includes(`/simulate/${OTHER_GAME_ID}/step/`)) return jsonResponse(claimB, 200);
      if (u.includes("/action/")) {
        actionCalls.push({
          url: u,
          body: JSON.parse(String(init?.body)) as Record<string, unknown>,
        });
        return jsonResponse({ ok: true }, 200);
      }
      throw new Error(`unexpected ${u}`);
    });
    const first = POST(
      turnRequest(USER_GAME_ID, { expected_move_count: 0 }, { Authorization: "Bearer staff-a" }),
      contextFor(USER_GAME_ID),
    );
    const second = POST(
      turnRequest(OTHER_GAME_ID, { expected_move_count: 0 }, { Authorization: "Bearer staff-b" }),
      contextFor(OTHER_GAME_ID),
    );
    await Promise.all([first, second]);
    expect(executeAiMoveMock).toHaveBeenCalledTimes(2);
    expect(actionCalls).toHaveLength(2);
    expect(
      actionCalls.map((call) => call.url).sort(),
    ).toEqual(
      [
        `http://localhost:8000/api/admin/simulate/${USER_GAME_ID}/action/`,
        `http://localhost:8000/api/admin/simulate/${OTHER_GAME_ID}/action/`,
      ].sort(),
    );
    expect(
      actionCalls.map((call) => call.body.lease_id).sort(),
    ).toEqual([claimA.lease_id, claimB.lease_id].sort());
  });

  it("sets private no-store JSON and SSE cache headers with Vary Authorization", async () => {
    stubBackend(async () => {
      throw new Error("down");
    });
    const error = await POST(
      turnRequest(USER_GAME_ID, { expected_move_count: 0 }, {
        Authorization: "Bearer staff-token",
      }),
      contextFor(USER_GAME_ID),
    );
    expect(error.status).toBe(503);
    expect(error.headers.get("Cache-Control")).toBe("private, no-store");
    expect(error.headers.get("Vary")).toContain("Authorization");

    vi.unstubAllGlobals();
    stubBackend(async (url) => {
      if (String(url).endsWith("/step/")) {
        return jsonResponse(
          { kind: "cpu", state: { simulation_schema_version: 1, game_id: USER_GAME_ID } },
          200,
        );
      }
      throw new Error(`unexpected ${url}`);
    });
    const sse = await POST(
      turnRequest(USER_GAME_ID, { expected_move_count: 0 }, {
        Authorization: "Bearer staff-token",
      }),
      contextFor(USER_GAME_ID),
    );
    expect(sse.status).toBe(200);
    expect(sse.headers.get("Cache-Control")).toBe("private, no-store, no-transform");
    expect(sse.headers.get("Vary")).toContain("Authorization");
    expect(sse.headers.get("Content-Type")).toContain("text/event-stream");
  });
});