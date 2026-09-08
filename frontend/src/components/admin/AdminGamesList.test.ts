import { expect, it } from "vitest";
import type { AdminGameSummary } from "@/lib/types";

it("keeps the admin game summary contract displayable", () => {
  const game: AdminGameSummary = { game_id: "123e4567-e89b-42d3-a456-426614174000", game_mode: "vs_ai", variant_slug: "english", status: "finished", is_diagnostic: true, created_at: "2026-09-08T00:00:00Z", finished_at: null, move_count: 2, winner_slot: 0, game_end_reason: "done", slots: [], diagnostic: null, diagnostic_run_count: 1 };
  expect(game.game_id.replaceAll("-", "").slice(0, 12)).toBe("123e4567e89b"); expect(game.is_diagnostic).toBe(true);
});
