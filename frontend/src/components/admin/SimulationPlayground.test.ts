import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SimulationArena } from "./SimulationArena";
import type { SimulationState } from "@/lib/admin-simulation";

function state(): SimulationState {
  return {
    simulation_schema_version: 1,
    game_id: "game-1",
    config: { version: 1, variant_slug: "english", seed: 0, ai_timeout: 30, ai_max_steps: 10, slots: [] },
    status: "finished",
    variant_slug: "english",
    board: Array.from({ length: 15 }, () => Array(15).fill(null)),
    premium_used: [], racks: [["?"], ["SZ"]], scores: [-2, 4],
    players: [{ slot: 0, username: null, score: -2, is_ai: true, model_id: "engine/cpu", model_display_name: "CPU Master" }, { slot: 1, username: null, score: 4, is_ai: true, model_id: "model", model_display_name: "Rival" }],
    tile_points: { SZ: 4, "?": 0 }, bag_remaining: 0, move_count: 1, current_turn_slot: null,
    game_over: true, game_end_reason: "rack_empty", winner_slot: 1, in_flight: false,
    latest_move: null, moves: [{ seq: 1, kind: "pass", player_slot: 0, placements: [], words: [], points: 0, tiles_exchanged: 0, created_at: "", ai_metadata: {} }],
    replay_url: "/admin/replay/game-1",
  };
}

describe("simulation arena", () => {
  it("renders terminal scores, commentary, and Replay Studio transition", () => {
    const markup = renderToStaticMarkup(createElement(SimulationArena, { state: state(), phase: "finished", speed: 1, status: null, onPause() {}, onResume() {}, onStep() {}, onStop() {}, onSpeed() {} }));
    expect(markup).toContain("Rival wins");
    expect(markup).toContain("spread -6");
    expect(markup).toContain("CPU Master passed");
    expect(markup).toContain("Open in Replay Studio");
    expect(markup).toContain("Live simulation board");
  });
});
