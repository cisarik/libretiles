export interface Placement {
  row: number;
  col: number;
  letter: string;
  blank_as?: string | null;
}

export interface WordResult {
  word: string;
  score: number;
  multiplier?: number;
  coords?: Array<{ row: number; col: number }>;
}

export interface SlotInfo {
  slot: number;
  username: string | null;
  score: number;
  rack_count: number;
  is_ai: boolean;
  pass_streak: number;
}

export interface ChatMessage {
  id: number;
  author_slot: number | null;
  author_username: string;
  body: string;
  created_at: string;
  mine: boolean;
}

export interface MoveHistoryItem {
  seq: number;
  kind: "place" | "exchange" | "pass" | "give_up";
  player_slot: number | null;
  placements: Placement[];
  words: WordResult[];
  points: number;
  created_at: string;
}

export interface GameState {
  game_id: string;
  status: "waiting" | "active" | "finished" | "abandoned";
  game_mode: "vs_ai" | "vs_human";
  variant_slug: string;
  board: string[];
  blanks: { row: number; col: number }[];
  premium_used: { row: number; col: number }[];
  bag_remaining: number;
  current_turn_slot: number | null;
  game_over: boolean;
  game_end_reason: string;
  winner_slot: number | null;
  my_slot: number;
  ai_model_id: string | null;
  ai_model_display_name?: string | null;
  ai_prompt_id?: number | null;
  ai_prompt_name?: string | null;
  ai_prompt_fitness?: number | null;
  slots: SlotInfo[];
  move_count: number;
  my_rack: string[];
  move_history: MoveHistoryItem[];
  chat_messages: ChatMessage[];
  last_move_cells?: Placement[];
  last_move_points?: number;
  last_move_words?: WordResult[];
  last_move_player_slot?: number | null;
}

export interface StartingDraw {
  human_tile: string;
  ai_tile: string;
  human_first: boolean;
}

export interface CreateGameResponse {
  game_id: string;
  starting_draw: StartingDraw;
  human_rack: string[];
  current_turn_slot: number | null;
  ai_model_id: string | null;
  ai_model_display_name?: string | null;
  ai_prompt_id?: number | null;
  ai_prompt_name?: string | null;
}

export interface QueueJoinResponse {
  ok: boolean;
  waiting: boolean;
  matched: boolean;
  state: GameState;
}

export interface WSTicketResponse {
  ok: boolean;
  ticket: string;
  expires_in: number;
}

export type GameHistoryFilter = "all" | "vs_ai" | "vs_human";
export type GameHistorySort = "updated";
export type GameHistoryOutcome =
  | "waiting"
  | "in_progress"
  | "won"
  | "lost"
  | "gave_up"
  | "abandoned";

export interface GameHistoryItem {
  game_id: string;
  game_mode: "vs_ai" | "vs_human";
  status: "waiting" | "active" | "finished" | "abandoned";
  outcome: GameHistoryOutcome;
  opponent_label: string;
  ai_model_display_name?: string | null;
  my_score: number;
  opponent_score: number;
  move_count: number;
  is_my_turn: boolean;
  winner_slot: number | null;
  game_end_reason: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface GameHistoryResponse {
  items: GameHistoryItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
  game_mode: GameHistoryFilter;
  sort: GameHistorySort;
}

export interface MoveResult {
  ok: boolean;
  error?: string;
  invalid_words?: string[];
  points?: number;
  bingo?: boolean;
  words?: WordResult[];
  new_rack?: string[];
  bag_remaining?: number;
  game_over?: boolean;
  game_end_reason?: string;
  final_scores?: Record<string, number>;
  leftover_points?: Record<string, number>;
  winner_slot?: number | null;
  action?: string;
  state?: GameState;
}

export interface MoveValidationResult {
  valid: boolean;
  reason?: string;
  total_score?: number;
  words?: Array<{ word: string; valid: boolean }>;
  breakdowns?: Array<{ word: string; score: number; multiplier?: number }>;
}

export interface AIModel {
  id: number;
  provider: string;
  model_id: string;
  display_name: string;
  description: string;
  quality_tier: "basic" | "standard" | "premium" | "elite";
  context_window?: number | null;
  max_tokens?: number | null;
  is_flagship: boolean;
}

export interface AIPrompt {
  id: number;
  name: string;
  prompt: string;
  fitness: number;
}

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  preferred_ai_model_id: string;
  date_joined: string;
}

export type PremiumType = "TW" | "DW" | "TL" | "DL" | "";

// AI thinking overlay types

export type AiFallbackAttemptStatus = "pending" | "active" | "failed";

export interface AiFallbackAttempt {
  provider: string;
  modelId: string;
  status: AiFallbackAttemptStatus;
}

export interface AICandidate {
  word: string;
  score: number;
  valid: boolean;
  isBest: boolean;
  timestamp: number;
  allWords?: string[];
  placements?: Placement[];
}

export type AIProgressEventType =
  | "thinking"
  | "tool_use"
  | "tool_result"
  | "candidate"
  | "done"
  | "error";

export interface AIProgressEvent {
  type: AIProgressEventType;
  data: Record<string, unknown>;
}

/** Slice-2 terminal diagnostics. Transient UI only — never persist. */
export type AiCompletionSource =
  | "provider_candidate"
  | "repair_candidate"
  | "backend_witness_rescue"
  | "genuine_no_move_exchange"
  | "genuine_no_move_pass";

export interface AiTurnTelemetry {
  completionSource?: AiCompletionSource | null;
  probeStatus?: string | null;
  repairAttempted?: boolean | null;
  terminalCause?: string | null;
  humanState?: string | null;
}

const COMPLETION_SOURCES: ReadonlySet<string> = new Set([
  "provider_candidate",
  "repair_candidate",
  "backend_witness_rescue",
  "genuine_no_move_exchange",
  "genuine_no_move_pass",
]);

export function asAiCompletionSource(
  value: unknown,
): AiCompletionSource | null {
  return typeof value === "string" && COMPLETION_SOURCES.has(value)
    ? (value as AiCompletionSource)
    : null;
}

/**
 * Concise overlay copy for turn diagnostics. Unknown combinations stay silent
 * so provider-candidate noise does not replace the live search status.
 */
export function describeAiTurnTelemetry(input: {
  completionSource?: string | null;
  probeStatus?: string | null;
  repairAttempted?: boolean | null;
  terminalCause?: string | null;
  thinkingStatus?: string | null;
  message?: string | null;
  providersExhausted?: boolean;
}): string | null {
  if (input.providersExhausted) return "providers exhausted";
  const message = input.message?.trim() ?? "";
  if (message === "backend found a legal rescue; repairing") return message;
  if (message === "genuine dead rack — exchanging") return message;
  if (message === "genuine dead rack — passing") return message;
  if (message === "providers exhausted") return message;
  if (
    input.thinkingStatus === "probe_found" ||
    (input.probeStatus === "found" &&
      (input.repairAttempted === true ||
        input.completionSource === "repair_candidate" ||
        input.completionSource === "backend_witness_rescue"))
  ) {
    return "backend found a legal rescue; repairing";
  }
  if (
    input.completionSource === "genuine_no_move_exchange" ||
    input.thinkingStatus === "genuine_exchange"
  ) {
    return "genuine dead rack — exchanging";
  }
  if (
    input.completionSource === "genuine_no_move_pass" ||
    input.thinkingStatus === "genuine_pass"
  ) {
    return "genuine dead rack — passing";
  }
  return null;
}
