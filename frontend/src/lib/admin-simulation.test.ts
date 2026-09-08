import { describe, expect, it } from "vitest";

import { parseSimulationState, simulationLatestDelta } from "./admin-simulation";

function fixture() {
  return {
    simulation_schema_version: 1,
    game_id: "game-1",
    config: { version: 1, variant_slug: "english", seed: 0, ai_timeout: 30, ai_max_steps: 10, slots: [] },
    status: "active",
    variant_slug: "english",
    board: Array.from({ length: 15 }, () => Array(15).fill(null)),
    premium_used: [],
    racks: [[], []],
    scores: [0, 0],
    players: [],
    tile_points: {},
    bag_remaining: 86,
    move_count: 1,
    current_turn_slot: 1,
    game_over: false,
    game_end_reason: "",
    winner_slot: null,
    in_flight: false,
    latest_move: { seq: 1, kind: "place", player_slot: 0, placements: [{ row: 7, col: 7, letter: "?", blank_as: "SZ" }], words: [], points: 0, tiles_exchanged: 0, created_at: "", ai_metadata: {} },
    moves: [],
    replay_url: "/admin/replay/game-1",
  };
}

describe("simulation ingress", () => {
  it("accepts v1 and preserves blank assignment in latest delta", () => {
    const state = parseSimulationState(fixture());
    expect(simulationLatestDelta(state)).toEqual([
      { row: 7, col: 7, token: "?", blank_as: "SZ" },
    ]);
  });

  it("refuses unknown schemas", () => {
    expect(() => parseSimulationState({ ...fixture(), simulation_schema_version: 2 })).toThrow(
      "unsupported state",
    );
  });
});
