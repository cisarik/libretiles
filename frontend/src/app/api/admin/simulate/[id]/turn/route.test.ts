import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/app/api/ai/move/route", () => ({
  executeAiMoveInternal: vi.fn(async () => new Response("data: {\"type\":\"done\"}\n\n", {
    headers: { "Content-Type": "text/event-stream" },
  })),
}));

import { POST } from "./route";

const context = { params: Promise.resolve({ id: "game-1" }) } as RouteContext<
  "/api/admin/simulate/[id]/turn"
>;

describe("admin simulation turn route", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("rejects missing authentication before claiming a turn", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const response = await POST(
      new NextRequest("http://localhost/api/admin/simulate/game-1/turn", {
        method: "POST",
        body: JSON.stringify({ expected_move_count: 0 }),
      }),
      context,
    );
    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("short-circuits CPU turns without invoking a provider", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ kind: "cpu", state: { game_id: "game-1" } }), { status: 200 })));
    const response = await POST(
      new NextRequest("http://localhost/api/admin/simulate/game-1/turn", {
        method: "POST",
        headers: { Authorization: "Bearer staff-token" },
        body: JSON.stringify({ expected_move_count: 0 }),
      }),
      context,
    );
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(await response.text()).toContain('"turn_provider_requests_used":0');
  });
});
