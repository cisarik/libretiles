import { z } from "zod";
import { BOARD_SIZE } from "@/lib/constants";
import type { AdminReplayPayload, BoardCell } from "@/lib/types";

const slot = z.number().int().min(0).max(1);
const coordinate = z.number().int().min(0).max(BOARD_SIZE - 1);
const token = z.string().min(1);
const boardCell = z.union([
  z.null(),
  z.object({ token, blank_as: z.string().min(1).nullable() }).superRefine((cell, context) => {
    if ((cell.token === "?") !== (cell.blank_as !== null)) {
      context.addIssue({ code: "custom", message: "Blank cells require token ? and an assignment" });
    }
  }),
]);
const board = z.array(z.array(boardCell).length(BOARD_SIZE)).length(BOARD_SIZE);
const rackPair = z.tuple([z.array(token).nullable(), z.array(token).nullable()]);
const scorePair = z.tuple([z.number().nullable(), z.number().nullable()]);
const placement = z.object({ row: coordinate, col: coordinate, letter: token, blank_as: token.nullable().optional() });
const wordInspection = z.object({
  version: z.literal(1),
  physical_cells: z.array(z.object({
    row: coordinate, col: coordinate, token, blank_as: token.nullable(), base_points: z.number().int().min(0),
    is_new: z.boolean(), premium: z.enum(["DL", "TL", "DW", "TW"]).nullable(), premium_applied: z.boolean(), letter_multiplier: z.number().int().min(1).max(3),
  })),
  base_points: z.number().int().min(0), letter_bonus_points: z.number().int().min(0), word_multiplier: z.number().int().min(1), word_total: z.number().int().min(0),
  authority: z.object({
    name: z.literal("WordAuthority"), valid: z.literal(true), physical_tile_count: z.number().int().min(1), route: z.enum(["main", "two_tile", "forbidden"]),
    main_lexicon_id: z.string(), two_tile_lexicon_id: z.string().nullable(), lexicon_source: z.string(),
  }),
});
const word = z.object({
  word: token,
  score: z.number(),
  multiplier: z.number().optional(),
  coords: z.array(z.object({ row: coordinate, col: coordinate })).optional(),
  inspection: wordInspection.optional(),
});
const delta = z.object({ row: coordinate, col: coordinate, token, blank_as: token.nullable() }).superRefine((cell, context) => {
  if ((cell.token === "?") !== (cell.blank_as !== null)) {
    context.addIssue({ code: "custom", message: "Malformed replay board delta" });
  }
});
const player = z.object({
  slot,
  username: z.string().nullable(),
  score: z.number(),
  is_ai: z.boolean(),
  model_id: z.string().nullable(),
  model_display_name: z.string().nullable(),
});
const diagnosticPly = z.object({
  id: z.number().int(), run_id: z.string(), ply_index: z.number().int(), position_index: z.number().int().nullable(),
  seat_index: slot, model_id: z.string(), assist_mode: z.string(), score_authority: z.string(),
  model_authored: z.boolean().nullable(), first_validate_valid: z.boolean().nullable(), valid_candidate_count: z.number().int().nullable(),
  model_legal_score: z.number().nullable(), ranked_best_score: z.number().nullable(), ranked_search_complete: z.boolean().nullable(),
  give_up_while_legal: z.boolean().nullable(), playability_status: z.string().nullable(), completion_source: z.string().nullable(),
  terminal_cause: z.string().nullable(), provider_requests_used: z.number().int().nullable(), steps_consumed: z.number().int().nullable(),
  wall_clock_ms: z.number().int().nullable(), malformed_or_non_tool: z.boolean().nullable(), fallback_attempt_index: z.number().int().nullable(),
  earlier_attempt_failures: z.json(), executed_runtime_mode: z.string().nullable(), ai_trace: z.json(), created_at: z.string(),
});
const replaySchema = z.object({
  replay_schema_version: z.literal(1), game_id: z.string(), variant_slug: z.string(), game_mode: z.enum(["vs_ai", "vs_human"]),
  status: z.enum(["waiting", "active", "finished", "abandoned"]), winner_slot: slot.nullable(), game_end_reason: z.string(),
  created_at: z.string(), finished_at: z.string().nullable(), tile_points: z.record(z.string(), z.number()), alphabet: z.array(token),
  players: z.array(player),
  initial_state: z.object({ initial_board: board.nullable(), initial_racks: rackPair, initial_scores: scorePair, starting_turn_slot: slot.nullable(), bag_seed: z.number().int() }),
  plies: z.array(z.object({
    seq: z.number().int(), player_slot: slot, kind: z.enum(["place", "exchange", "pass", "give_up"]), created_at: z.string(),
    placements: z.array(placement), words_formed: z.array(word), points: z.number(), tiles_exchanged: z.number().int().min(0),
    exchanged_tiles: z.array(token).nullable(), cumulative_scores: scorePair, racks: rackPair, board_delta: z.array(delta),
    ai_metadata: z.record(z.string(), z.json()), diagnostic_ply: diagnosticPly.nullable(),
  })),
  final_state: z.object({ board, racks: z.tuple([z.array(token), z.array(token)]), scores: z.tuple([z.number(), z.number()]) }),
  replay_status: z.enum(["complete", "partial"]),
}).superRefine((payload, context) => {
  for (let index = 0; index < payload.plies.length; index += 1) {
    const current = payload.plies[index];
    if (index > 0 && current.seq <= payload.plies[index - 1].seq) {
      context.addIssue({ code: "custom", path: ["plies", index, "seq"], message: "Replay sequences must increase" });
    }
    if ((current.kind === "place") !== (current.board_delta.length > 0)) {
      context.addIssue({ code: "custom", path: ["plies", index, "board_delta"], message: "Board deltas must describe placement moves only" });
    }
  }
});

export interface ReplayFrame {
  board: BoardCell[][] | null;
  racks: [string[] | null, string[] | null];
  scores: [number | null, number | null];
}

export function parseAdminReplay(value: unknown): AdminReplayPayload {
  return replaySchema.parse(value) as AdminReplayPayload;
}

export function buildReplayFrames(payload: AdminReplayPayload): ReplayFrame[] {
  const initialBoard = payload.initial_state.initial_board?.map((row) => row.map((cell) => cell && { ...cell })) ?? null;
  const frames: ReplayFrame[] = [{
    board: initialBoard,
    racks: payload.initial_state.initial_racks.map((rack) => rack && [...rack]) as ReplayFrame["racks"],
    scores: [...payload.initial_state.initial_scores] as ReplayFrame["scores"],
  }];
  for (const ply of payload.plies) {
    const previous = frames[frames.length - 1];
    let nextBoard = previous.board;
    if (nextBoard && ply.board_delta.length) {
      const changedRows = new Map<number, BoardCell[]>();
      nextBoard = [...nextBoard];
      for (const item of ply.board_delta) {
        const row = changedRows.get(item.row) ?? [...nextBoard[item.row]];
        row[item.col] = { token: item.token, blank_as: item.blank_as };
        changedRows.set(item.row, row);
        nextBoard[item.row] = row;
      }
    }
    frames.push({ board: nextBoard, racks: ply.racks, scores: ply.cumulative_scores });
  }
  return frames;
}

export function boardMatches(a: BoardCell[][] | null, b: BoardCell[][]): boolean {
  return a !== null && JSON.stringify(a) === JSON.stringify(b);
}
