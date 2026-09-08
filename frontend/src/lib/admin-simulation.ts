import type { AdminReplayPlayer, BoardCell, Placement, WordResult } from "./types";

export type SimulationSlotConfig =
  | { kind: "cpu" }
  | { kind: "llm"; provider: string; model_id: string; prompt_id: number | null };

export type SimulationConfig = {
  slot0: SimulationSlotConfig;
  slot1: SimulationSlotConfig;
  variant_slug: string;
  seed?: number;
  ai_timeout: number;
  ai_max_steps: number;
};

export type SimulationMove = {
  seq: number;
  kind: "place" | "exchange" | "pass" | "give_up";
  player_slot: number;
  placements: Placement[];
  words: WordResult[];
  points: number;
  tiles_exchanged: number;
  created_at: string;
  ai_metadata: Record<string, unknown>;
};

export type SimulationState = {
  simulation_schema_version: 1;
  game_id: string;
  config: {
    version: 1;
    variant_slug: string;
    seed: number;
    ai_timeout: number;
    ai_max_steps: number;
    slots: Array<{
      kind: "cpu" | "llm";
      provider: string;
      model_id: string;
      display_name: string;
      prompt_id: number | null;
      prompt_name: string | null;
    }>;
  };
  status: "active" | "finished" | "abandoned";
  variant_slug: string;
  board: BoardCell[][];
  premium_used: Array<{ row: number; col: number }>;
  racks: [string[], string[]];
  scores: [number, number];
  players: AdminReplayPlayer[];
  tile_points: Record<string, number>;
  bag_remaining: number;
  move_count: number;
  current_turn_slot: number | null;
  game_over: boolean;
  game_end_reason: string;
  winner_slot: number | null;
  in_flight: boolean;
  latest_move: SimulationMove | null;
  moves: SimulationMove[];
  replay_url: string;
};

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function parseSimulationState(value: unknown): SimulationState {
  const input = record(value);
  if (
    !input ||
    input.simulation_schema_version !== 1 ||
    typeof input.game_id !== "string" ||
    !Array.isArray(input.board) ||
    input.board.length !== 15 ||
    !Array.isArray(input.racks) ||
    input.racks.length !== 2 ||
    !Array.isArray(input.scores) ||
    input.scores.length !== 2 ||
    !Array.isArray(input.players) ||
    !Array.isArray(input.moves)
  ) {
    throw new Error("The simulation server returned an unsupported state.");
  }
  return input as unknown as SimulationState;
}

export function simulationLatestDelta(state: SimulationState) {
  if (state.latest_move?.kind !== "place") return [];
  return state.latest_move.placements.map((placement) => ({
    row: placement.row,
    col: placement.col,
    token: placement.blank_as ? "?" : placement.letter,
    blank_as: placement.blank_as ?? null,
  }));
}
