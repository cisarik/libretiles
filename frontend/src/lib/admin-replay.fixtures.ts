import type { AdminReplayPayload, BoardCell } from "./types";

export const emptyAdminBoard = (): BoardCell[][] => Array.from({ length: 15 }, () => Array<BoardCell>(15).fill(null));

export function adminReplayFixture(): AdminReplayPayload {
  const board = emptyAdminBoard();
  const finalBoard = emptyAdminBoard();
  finalBoard[7][7] = { token: "?", blank_as: "SZ" };
  return {
    replay_schema_version: 1, game_id: "123e4567-e89b-42d3-a456-426614174000", variant_slug: "english", game_mode: "vs_ai",
    status: "finished", winner_slot: 0, game_end_reason: "bag_empty", created_at: "2026-09-08T10:00:00Z", finished_at: "2026-09-08T10:10:00Z",
    tile_points: { A: 1, SZ: 4, "?": 0 }, alphabet: ["A", "SZ", "?"],
    players: [
      { slot: 0, username: "Ada", score: 12, is_ai: false, model_id: null, model_display_name: null },
      { slot: 1, username: null, score: 0, is_ai: true, model_id: "bot/model", model_display_name: "Bot Model" },
    ],
    initial_state: { initial_board: board, initial_racks: [["?", "A"], ["SZ"]], initial_scores: [0, 0], starting_turn_slot: 0, bag_seed: 12 },
    plies: [
      { seq: 1, player_slot: 0, kind: "place", created_at: "2026-09-08T10:01:00Z", placements: [{ row: 7, col: 7, letter: "?", blank_as: "SZ" }], words_formed: [{ word: "SZ", score: 12, multiplier: 2, coords: [{ row: 7, col: 7 }] }], points: 12, tiles_exchanged: 0, exchanged_tiles: null, cumulative_scores: [12, 0], racks: [["A"], ["SZ"]], board_delta: [{ row: 7, col: 7, token: "?", blank_as: "SZ" }], ai_metadata: {}, diagnostic_ply: null },
      { seq: 2, player_slot: 1, kind: "pass", created_at: "2026-09-08T10:02:00Z", placements: [], words_formed: [], points: 0, tiles_exchanged: 0, exchanged_tiles: null, cumulative_scores: [12, 0], racks: [["A"], ["SZ"]], board_delta: [], ai_metadata: {}, diagnostic_ply: null },
    ],
    final_state: { board: finalBoard, racks: [["A"], ["SZ"]], scores: [12, 0] }, replay_status: "complete",
  };
}
