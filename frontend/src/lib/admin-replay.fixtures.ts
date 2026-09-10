import type { AdminReplayPayload, BoardCell } from "./types";

export const emptyAdminBoard = (): BoardCell[][] => Array.from({ length: 15 }, () => Array<BoardCell>(15).fill(null));

export function adminReplayFixture(): AdminReplayPayload {
  const board = emptyAdminBoard();
  const finalBoard = emptyAdminBoard();
  finalBoard[7][7] = { token: "A", blank_as: null };
  finalBoard[7][8] = { token: "T", blank_as: null };
  return {
    replay_schema_version: 1, game_id: "123e4567-e89b-42d3-a456-426614174000", variant_slug: "english", game_mode: "vs_ai",
    status: "finished", winner_slot: 0, game_end_reason: "bag_empty", created_at: "2026-09-08T10:00:00Z", finished_at: "2026-09-08T10:10:00Z",
    tile_points: { A: 1, T: 1, "?": 0 }, alphabet: ["A", "T", "?"],
    players: [
      { slot: 0, username: "Ada", score: 4, is_ai: false, model_id: null, model_display_name: null },
      { slot: 1, username: null, score: 0, is_ai: true, model_id: "bot/model", model_display_name: "Bot Model" },
    ],
    initial_state: { initial_board: board, initial_racks: [["A", "T"], ["?", "B"]], initial_scores: [0, 0], starting_turn_slot: 0, bag_seed: 12 },
    plies: [
      { seq: 1, player_slot: 0, kind: "place", created_at: "2026-09-08T10:01:00Z", placements: [{ row: 7, col: 7, letter: "A" }, { row: 7, col: 8, letter: "T" }], words_formed: [{ word: "AT", score: 4, multiplier: 2, coords: [{ row: 7, col: 7 }, { row: 7, col: 8 }], inspection: { version: 1, physical_cells: [{ row: 7, col: 7, token: "A", blank_as: null, base_points: 1, is_new: true, premium: "DW", premium_applied: true, letter_multiplier: 1 }, { row: 7, col: 8, token: "T", blank_as: null, base_points: 1, is_new: true, premium: null, premium_applied: false, letter_multiplier: 1 }], base_points: 2, letter_bonus_points: 0, word_multiplier: 2, word_total: 4, authority: { name: "WordAuthority", valid: true, physical_tile_count: 2, route: "main", main_lexicon_id: "collins2019", two_tile_lexicon_id: null, lexicon_source: "Collins Scrabble Words (2019)" } } }], points: 4, tiles_exchanged: 0, exchanged_tiles: null, cumulative_scores: [4, 0], racks: [[], ["?", "B"]], board_delta: [{ row: 7, col: 7, token: "A", blank_as: null }, { row: 7, col: 8, token: "T", blank_as: null }], ai_metadata: { completion_source: "provider_candidate", inspection_trace: { version: 1, attempts: [{ attempt_index: 0, provider: "openrouter", model_id: "bot/model", latency_ms: 210, provider_requests_used: 2, outcome: "done", events: [{ ordinal: 0, elapsed_ms: 100, phase: "search", tool: "validateMove", placements: [{ row: 7, col: 7, letter: "A" }, { row: 7, col: 8, letter: "T" }], words: ["AT"], valid: true, score: 4 }, { ordinal: 1, elapsed_ms: 200, phase: "finishMove", tool: "finishMove", ready: true }] }] } }, diagnostic_ply: null },
      { seq: 2, player_slot: 1, kind: "pass", created_at: "2026-09-08T10:02:00Z", placements: [], words_formed: [], points: 0, tiles_exchanged: 0, exchanged_tiles: null, cumulative_scores: [4, 0], racks: [[], ["?", "B"]], board_delta: [], ai_metadata: {}, diagnostic_ply: null },
    ],
    final_state: { board: finalBoard, racks: [[], ["?", "B"]], scores: [4, 0] }, replay_status: "complete",
  };
}
