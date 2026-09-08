import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());
describe("admin API", () => {
  it("encodes list filters and sends bearer auth without caching", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ count: 0, page: 1, total_pages: 1, page_size: 20, results: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetch); await api.admin.listGames("token", { game_mode: "vs_ai", search: "Ada Lovelace" });
    expect(fetch.mock.calls[0][0]).toContain("/api/admin/games/?game_mode=vs_ai&search=Ada+Lovelace");
    expect(fetch.mock.calls[0][1]).toMatchObject({ cache: "no-store", headers: expect.objectContaining({ Authorization: "Bearer token" }) });
  });
  it("encodes replay identifiers", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({}), { status: 200 })); vi.stubGlobal("fetch", fetch);
    await api.admin.getReplay("token", "id/value"); expect(fetch.mock.calls[0][0]).toContain("/api/admin/games/id%2Fvalue/replay/");
  });
});
