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
  billing?: BillingSummary | null;
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
  total_cost_usd: string;
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
  last_move_billing?: BillingSummary | null;
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

export interface BillingSummary {
  charged_credits: string;
  remaining_credits: string;
  charged_usd: string;
  charge_source: string;
  model_id: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export type GameHistoryFilter = "all" | "vs_ai" | "vs_human";
export type GameHistorySort = "updated" | "cost_desc";
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
  total_cost_usd: string;
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
  billing?: BillingSummary;
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
  cost_per_game: string;
  pricing: Record<string, unknown>;
  context_window?: number | null;
  max_tokens?: number | null;
  input_cost_per_million: string;
  output_cost_per_million: string;
  cache_read_cost_per_million: string;
  cache_write_cost_per_million: string;
  combined_cost_per_million: string;
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
  credit_balance: string;
  credit_updated_at?: string | null;
  date_joined: string;
}

export type PremiumType = "TW" | "DW" | "TL" | "DL" | "";

// AI thinking overlay types

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
