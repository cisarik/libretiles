import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { DualRackVisualizer } from "./DualRackVisualizer";
import { adminReplayFixture } from "@/lib/admin-replay.fixtures";

it("renders both ordered racks, blank accessibility, and acting seat", () => {
  const fixture = adminReplayFixture(); const markup = renderToStaticMarkup(createElement(DualRackVisualizer, { players: fixture.players, racks: fixture.initial_state.initial_racks, scores: fixture.initial_state.initial_scores, actingSlot: 0, currentPlyIndex: 0, tilePoints: fixture.tile_points, premium: false }));
  expect(markup).toContain("Player 0 rack"); expect(markup).toContain("Player 1 rack"); expect(markup).toContain("Starting player"); expect(markup).toContain("Blank tile, zero points"); expect(markup).toContain("Bot Model");
});

it("uses live turn wording in simulation mode", () => {
  const fixture = adminReplayFixture(); const markup = renderToStaticMarkup(createElement(DualRackVisualizer, { players: fixture.players, racks: fixture.initial_state.initial_racks, scores: fixture.initial_state.initial_scores, actingSlot: 1, currentPlyIndex: 2, tilePoints: fixture.tile_points, premium: false, live: true }));
  expect(markup).toContain("Thinking");
});
