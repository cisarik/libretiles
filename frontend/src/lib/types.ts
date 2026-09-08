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
  inspection?: AdminWordInspection;
}

export interface AdminScoreCellInspection {
  row: number;
  col: number;
  token: string;
  blank_as: string | null;
  base_points: number;
  is_new: boolean;
  premium: "DL" | "TL" | "DW" | "TW" | null;
  premium_applied: boolean;
  letter_multiplier: number;
}

export interface AdminWordInspection {
  version: 1;
  physical_cells: AdminScoreCellInspection[];
  base_points: number;
  letter_bonus_points: number;
  word_multiplier: number;
  word_total: number;
  authority: {
    name: "WordAuthority";
    valid: true;
    physical_tile_count: number;
    route: "main" | "two_tile" | "forbidden";
    main_lexicon_id: string;
    two_tile_lexicon_id: string | null;
    lexicon_source: string;
  };
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

/**
 * Version of the GAME-STATE WIRE payload this client can render.
 *
 * The client REFUSES a version it does not understand rather than
 * mis-rendering one: a guard that refuses is loud, a wrong board is silent.
 * The refusal lives in `setGameState`, the single ingress choke point for
 * every game-state payload, REST and websocket alike.
 *
 * Unrelated to the zustand persist `version`, and unrelated to the save-file
 * "schema 4" in the backend's `gamecore/state.py`.
 */
export const WIRE_STATE_SCHEMA_VERSION = 4;

export function isSupportedStateSchemaVersion(value: unknown): boolean {
  return value === WIRE_STATE_SCHEMA_VERSION;
}

/**
 * One board square as the wire carries it, or `null` when the square is empty.
 *
 * `token` is the ATOMIC tile token and MAY be several code points — "SZ",
 * "DZS", "L·L". `blank_as` is the letter a blank was played as, or `null`.
 * A blank arrives as `{ token: "?", blank_as: "SZ" }`, so the blank identity
 * travels inside its own cell and there is no sidecar `blanks` list to keep in
 * sync.
 */
export type BoardCell = { token: string; blank_as: string | null } | null;

/** The realized letter to render in a cell: the blank's assignment, else the tile. */
export function boardCellLetter(cell: BoardCell): string | null {
  if (!cell || !cell.token) return null;
  return cell.blank_as || cell.token;
}

export interface GameState {
  game_id: string;
  state_schema_version: number;
  status: "waiting" | "active" | "finished" | "abandoned";
  game_mode: "vs_ai" | "vs_human";
  variant_slug: string;
  board: BoardCell[][];
  premium_used: { row: number; col: number }[];
  bag_remaining: number;
  consecutive_scoreless_turns?: number;
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
  tile_points?: Record<string, number>;
  alphabet?: string[];
  lexicon_id?: string;
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

export type VariantReadiness = "playable" | "unavailable";

export interface VariantSummary {
  slug: string;
  display_name: string;
  language_code: string | null;
  readiness: VariantReadiness;
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
  | "draw"
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
  is_staff?: boolean;
}

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface AdminReplayPlayer {
  slot: number;
  username: string | null;
  score: number;
  is_ai: boolean;
  model_id: string | null;
  model_display_name: string | null;
}

export interface AdminDiagnosticSummary {
  run_id: string;
  status: string;
  assist_mode: string;
  instrument: string;
  model_ids: [string | null, string | null];
}

export interface AdminGameSummary {
  game_id: string;
  game_mode: "vs_ai" | "vs_human";
  variant_slug: string;
  status: "waiting" | "active" | "finished" | "abandoned";
  is_diagnostic: boolean;
  created_at: string;
  finished_at: string | null;
  move_count: number;
  winner_slot: number | null;
  game_end_reason: string;
  slots: AdminReplayPlayer[];
  diagnostic: AdminDiagnosticSummary | null;
  diagnostic_run_count: number;
}

export interface AdminGameListResponse {
  count: number;
  page: number;
  total_pages: number;
  page_size: number;
  results: AdminGameSummary[];
}

export interface AdminGameListParams {
  page?: number;
  page_size?: number;
  game_mode?: "all" | "vs_ai" | "vs_human";
  status?: "all" | "waiting" | "active" | "finished" | "abandoned";
  variant_slug?: string;
  search?: string;
  is_diagnostic?: "all" | "true" | "false";
}

export type AdminAnalyticsSource = "all" | "gameplay" | "playground" | "diagnostic";

export interface AdminAnalyticsModel {
  key: string;
  provider: string;
  model_id: string;
  display_name: string;
  source: string;
  runtime_mode: string;
  is_selectable: boolean;
  is_current_flagship: boolean;
  catalog_order: number;
  games_played: number;
  seat_appearances: number;
  completed_seats: number;
  wins: number;
  losses: number;
  draws: number;
  win_rate_pct: number | null;
  avg_score: number | null;
  avg_spread: number | null;
  total_moves: number;
  known_completion_source_moves: number;
  provider_candidate_pct: number | null;
  avg_attempt_latency_ms: number | null;
  measured_attempts: number;
  avg_provider_requests_per_turn: number | null;
  request_measured_turns: number;
}

export interface AdminAnalyticsPreset {
  prompt_id: number | null;
  name: string;
  games_played: number;
  seat_appearances: number;
  completed_seats: number;
  wins: number;
  losses: number;
  draws: number;
  win_rate_pct: number | null;
  avg_score: number | null;
  content_version_verified: false;
}

export interface AdminAnalyticsRecommendation {
  status: "catalog_default" | "observed_leader" | "available" | "insufficient_evidence";
  provider: string | null;
  model_id: string | null;
  display_name: string | null;
  prompt_id: number | null;
  prompt_name: string | null;
  reason_codes: string[];
  evidence: { completed_seats: number; measured_attempts: number; variant_slug: string | null };
}

export interface AdminAnalyticsResponse {
  analytics_schema_version: 1;
  as_of: string;
  filters: { days: number; source: AdminAnalyticsSource; variant_slug: string };
  summary: {
    total_games: number;
    finished_games: number;
    total_plies: number;
    variants_played: number;
    variants: Array<{ variant_slug: string; total_games: number; finished_games: number; total_plies: number }>;
    abandoned_games: number;
    diagnostic_runs: number;
  };
  models: AdminAnalyticsModel[];
  presets: AdminAnalyticsPreset[];
  recommendations: {
    current_flagship: AdminAnalyticsRecommendation;
    primary_flagship: AdminAnalyticsRecommendation;
    high_throughput_rival: AdminAnalyticsRecommendation;
    offline_cpu: AdminAnalyticsRecommendation;
    strategic_preset: AdminAnalyticsRecommendation;
    reliability_notes: string[];
    changes_catalog: false;
  };
  coverage: { unknown_runtime_moves: number; unknown_completion_source_moves: number; limitations: string[] };
}

export interface AdminAnalyticsParams {
  days?: number;
  source?: AdminAnalyticsSource;
  variant_slug?: string;
}

export interface AdminReplayBoardDelta {
  row: number;
  col: number;
  token: string;
  blank_as: string | null;
}

export interface AdminDiagnosticPly {
  id: number;
  run_id: string;
  ply_index: number;
  position_index: number | null;
  seat_index: number;
  model_id: string;
  assist_mode: string;
  score_authority: string;
  model_authored: boolean | null;
  first_validate_valid: boolean | null;
  valid_candidate_count: number | null;
  model_legal_score: number | null;
  ranked_best_score: number | null;
  ranked_search_complete: boolean | null;
  give_up_while_legal: boolean | null;
  playability_status: string | null;
  completion_source: string | null;
  terminal_cause: string | null;
  provider_requests_used: number | null;
  steps_consumed: number | null;
  wall_clock_ms: number | null;
  malformed_or_non_tool: boolean | null;
  fallback_attempt_index: number | null;
  earlier_attempt_failures: JsonValue;
  executed_runtime_mode: string | null;
  ai_trace: JsonValue;
  created_at: string;
}

export interface AdminReplayInitialState {
  initial_board: BoardCell[][] | null;
  initial_racks: [string[] | null, string[] | null];
  initial_scores: [number | null, number | null];
  starting_turn_slot: number | null;
  bag_seed: number;
}

export interface AdminReplayPly {
  seq: number;
  player_slot: number;
  kind: "place" | "exchange" | "pass" | "give_up";
  created_at: string;
  placements: Placement[];
  words_formed: WordResult[];
  points: number;
  tiles_exchanged: number;
  exchanged_tiles: string[] | null;
  cumulative_scores: [number | null, number | null];
  racks: [string[] | null, string[] | null];
  board_delta: AdminReplayBoardDelta[];
  ai_metadata: Record<string, JsonValue>;
  diagnostic_ply: AdminDiagnosticPly | null;
}

export interface AdminReplayFinalState {
  board: BoardCell[][];
  racks: [string[], string[]];
  scores: [number, number];
}

export interface AdminReplayPayload {
  replay_schema_version: 1;
  game_id: string;
  variant_slug: string;
  game_mode: "vs_ai" | "vs_human";
  status: "waiting" | "active" | "finished" | "abandoned";
  winner_slot: number | null;
  game_end_reason: string;
  created_at: string;
  finished_at: string | null;
  tile_points: Record<string, number>;
  alphabet: string[];
  players: AdminReplayPlayer[];
  initial_state: AdminReplayInitialState;
  plies: AdminReplayPly[];
  final_state: AdminReplayFinalState;
  replay_status: "complete" | "partial";
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
  | "backend_ranked_candidate"
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
  "backend_ranked_candidate",
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
  if (message === "model made no progress; using backend move") return message;
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
  if (
    input.terminalCause === "backend_rescue_error" ||
    input.terminalCause === "commit_rejected"
  ) {
    return "backend rescue failed";
  }
  if (input.terminalCause === "no_provider_progress_deadline") {
    return "model made no progress; using backend move";
  }
  return null;
}

export function describeAiMoveFailure(input: {
  message?: string | null;
  code?: string | null;
  terminalCause?: string | null;
  probeStatus?: string | null;
  repairAttempted?: boolean | null;
  completionSource?: string | null;
}): string {
  const described = describeAiTurnTelemetry({
    completionSource: input.completionSource,
    probeStatus: input.probeStatus,
    repairAttempted: input.repairAttempted,
    terminalCause: input.terminalCause,
    message: input.message,
  });
  if (described) return described;
  if (input.probeStatus) {
    return `playability ${input.probeStatus}`;
  }
  if (input.code === "ai_move_internal_error") {
    return "backend rescue failed";
  }
  if (typeof input.code === "string" && input.code.length > 0) {
    return `The AI turn could not be completed (${input.code}).`;
  }
  if (typeof input.terminalCause === "string" && input.terminalCause.length > 0) {
    return input.terminalCause.replace(/_/g, " ");
  }
  const message = input.message?.trim() ?? "";
  if (message.length > 0 && message !== "AI move failed") return message;
  return "The AI turn could not be completed.";
}

export type LostAiTurnAnchor = {
  moveCount: number;
  aiSlot: number;
};

export type LostAiTurnLatest = {
  game_over?: boolean;
  move_count?: number;
  current_turn_slot?: number | null;
} | null;

export function shouldHideLostAiTerminal(
  latest: LostAiTurnLatest,
  anchor: LostAiTurnAnchor,
): boolean {
  if (latest == null) return false;
  if (latest.game_over === true) return true;
  if (
    typeof latest.move_count === "number" &&
    latest.move_count > anchor.moveCount
  ) {
    return true;
  }
  if (
    latest.current_turn_slot !== undefined &&
    latest.current_turn_slot !== anchor.aiSlot
  ) {
    return true;
  }
  return false;
}
