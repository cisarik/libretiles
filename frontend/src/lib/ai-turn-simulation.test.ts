/**
 * Deterministic 300-turn causal simulation for playable-free-rivals.
 *
 * Invokes the real fallback orchestrator, exported POST /api/ai/move handler,
 * and SSE consumer. Mocks only provider generation (`ai.generateText`) and
 * HTTP transport (global `fetch` → stateful fake Django). Any unexpected
 * network URL fails the test.
 *
 * Scenario builders are exported so later prompt work can add turns without
 * rewriting the engine.
 */
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fixture from "../../tests/fixtures/playable-free-rivals.json";
import {
  buildFallbackQueue,
  orchestrateFallbackTurn,
  type CatalogPair,
  type ReconciliationView,
} from "./ai-fallback";
import { consumeAIStream } from "./ai-move-stream";

const harness = vi.hoisted(() => ({
  generateText: vi.fn(),
}));

vi.mock("ai", () => ({
  generateText: harness.generateText,
  stepCountIs: (n: number) => n,
  tool: (definition: unknown) => definition,
}));

import { POST } from "@/app/api/ai/move/route";

export type ProviderScript =
  | "valid_placement"
  | "valid_then_pass_text"
  | "malformed_output"
  | "invalid_then_repair"
  | "timeout_witness_rescue"
  | "commit_reject_reprobe_rescue"
  | "retryable_429_fallback"
  | "retryable_no_endpoints_fallback"
  | "highest_score_retained"
  | "genuine_exchange"
  | "genuine_pass"
  | "indeterminate_probe"
  | "no_valid_provider_candidate";

export type PlacementSpec = {
  row: number;
  col: number;
  letter: string;
  blank_as?: string;
};

export type LegalMoveSpec = {
  placements: PlacementSpec[];
  word: string;
  score: number;
};

export type SimTurn = {
  id: string;
  kind: "found" | "exchange" | "pass" | "indeterminate";
  script: ProviderScript;
  board: string[];
  rack: string[];
  legalMoves: LegalMoveSpec[];
  invalidPlacement: PlacementSpec[];
  witness: LegalMoveSpec | null;
  exchangeAllowed: boolean;
  exchangeLetters: string[];
  expectedAction: "place" | "exchange" | "pass" | "none";
  expectedSource?: string;
  afterBoard: string[];
  afterRack: string[];
  variant?: string;
  lexicon_id?: string;
  tile_points?: Record<string, number>;
  alphabet?: string[];
};

export type SimGame = {
  id: string;
  rival: CatalogPair;
  turns: SimTurn[];
};

type FixtureShape = {
  bootstrap_rivals: CatalogPair[];
  games_per_rival: number;
  ai_turns_per_game: number;
  found_games_per_rival: number;
  found_scripts: ProviderScript[];
  tiles: {
    found_rack: string[];
    rate: LegalMoveSpec;
    rates: LegalMoveSpec;
    invalid_placement: PlacementSpec[];
    exchange_rack: string[];
    exchange_after_rack: string[];
    pass_rack: string[];
  };
};

const DATA = fixture as FixtureShape;
const REPAIR_RESERVE = 2;
const TURN_MAX_STEPS = 10;

export function emptyBoard(): string[] {
  return Array.from({ length: 15 }, () => "...............");
}

export function placeOnBoard(
  board: string[],
  placements: PlacementSpec[],
): string[] {
  const next = board.map((row) => row.split(""));
  for (const tile of placements) {
    next[tile.row][tile.col] = tile.letter;
  }
  return next.map((row) => row.join(""));
}

export function remainingRack(rack: string[], placements: PlacementSpec[]): string[] {
  const left = [...rack];
  for (const tile of placements) {
    const index = left.indexOf(tile.letter);
    if (index >= 0) left.splice(index, 1);
  }
  return left;
}

function cloneBoard(board: string[]): string[] {
  return board.map((row) => row);
}

function placementKey(placements: PlacementSpec[]): string {
  return JSON.stringify(
    placements.map((tile) => ({
      row: tile.row,
      col: tile.col,
      letter: tile.letter,
      ...(tile.blank_as ? { blank_as: tile.blank_as } : {}),
    })),
  );
}

export function buildFoundTurn(
  id: string,
  script: ProviderScript,
  tiles = DATA.tiles,
): SimTurn {
  const board = emptyBoard();
  const rack = [...tiles.found_rack];
  const rate = tiles.rate;
  const rates = tiles.rates;
  const committed =
    script === "highest_score_retained" || script === "no_valid_provider_candidate"
      ? rates
      : rate;
  return {
    id,
    kind: "found",
    script,
    board,
    rack,
    legalMoves: [rate, rates],
    invalidPlacement: tiles.invalid_placement,
    witness: rate,
    exchangeAllowed: false,
    exchangeLetters: [],
    expectedAction: "place",
    expectedSource:
      script === "invalid_then_repair"
        ? "repair_candidate"
        : script === "timeout_witness_rescue" ||
            script === "commit_reject_reprobe_rescue"
          ? "backend_witness_rescue"
          : script === "no_valid_provider_candidate"
            ? "backend_ranked_candidate"
            : "provider_candidate",
    afterBoard: placeOnBoard(board, committed.placements),
    afterRack: remainingRack(rack, committed.placements),
  };
}

export function buildExchangeTurn(id: string, tiles = DATA.tiles): SimTurn {
  const board = emptyBoard();
  return {
    id,
    kind: "exchange",
    script: "genuine_exchange",
    board,
    rack: [...tiles.exchange_rack],
    legalMoves: [],
    invalidPlacement: tiles.invalid_placement,
    witness: null,
    exchangeAllowed: true,
    exchangeLetters: [...tiles.exchange_rack],
    expectedAction: "exchange",
    expectedSource: "genuine_no_move_exchange",
    afterBoard: cloneBoard(board),
    afterRack: [...tiles.exchange_after_rack],
  };
}

export function buildPassTurn(id: string, tiles = DATA.tiles): SimTurn {
  const board = emptyBoard();
  return {
    id,
    kind: "pass",
    script: "genuine_pass",
    board,
    rack: [...tiles.pass_rack],
    legalMoves: [],
    invalidPlacement: tiles.invalid_placement,
    witness: null,
    exchangeAllowed: false,
    exchangeLetters: [],
    expectedAction: "pass",
    expectedSource: "genuine_no_move_pass",
    afterBoard: cloneBoard(board),
    afterRack: [...tiles.pass_rack],
  };
}

export function buildIndeterminateTurn(id: string, tiles = DATA.tiles): SimTurn {
  const board = emptyBoard();
  return {
    id,
    kind: "indeterminate",
    script: "indeterminate_probe",
    board,
    rack: [...tiles.found_rack],
    legalMoves: [],
    invalidPlacement: tiles.invalid_placement,
    witness: null,
    exchangeAllowed: false,
    exchangeLetters: [],
    expectedAction: "none",
    afterBoard: cloneBoard(board),
    afterRack: [...tiles.found_rack],
  };
}

export function buildReplayGames(data: FixtureShape = DATA): SimGame[] {
  const games: SimGame[] = [];
  for (const rival of data.bootstrap_rivals) {
    for (let gameIndex = 0; gameIndex < data.games_per_rival; gameIndex += 1) {
      const turns: SimTurn[] = [];
      if (gameIndex < data.found_games_per_rival) {
        for (let turnIndex = 0; turnIndex < data.ai_turns_per_game; turnIndex += 1) {
          const script =
            data.found_scripts[
              (gameIndex * data.ai_turns_per_game + turnIndex) %
                data.found_scripts.length
            ];
          turns.push(
            buildFoundTurn(`${rival.model_id}:${gameIndex}:${turnIndex}`, script),
          );
        }
      } else {
        for (let turnIndex = 0; turnIndex < 3; turnIndex += 1) {
          turns.push(
            buildExchangeTurn(`${rival.model_id}:${gameIndex}:ex:${turnIndex}`),
          );
        }
        for (let turnIndex = 0; turnIndex < 3; turnIndex += 1) {
          turns.push(
            buildPassTurn(`${rival.model_id}:${gameIndex}:pass:${turnIndex}`),
          );
        }
      }
      games.push({
        id: `sim-${rival.model_id}-${gameIndex}`,
        rival,
        turns,
      });
    }
  }
  return games;
}

type GenerationOpts = {
  temperature?: number;
  stopWhen?: unknown;
  abortSignal?: AbortSignal;
  tools?: {
    validateMove?: { execute?: (input: { placements: PlacementSpec[] }) => Promise<unknown> };
  };
  onStepFinish?: (step: {
    stepNumber: number;
    toolCalls: unknown[];
    usage: object;
    model: { provider: string; modelId: string };
    response: { modelId: string };
  }) => void;
};

type EngineState = {
  turn: SimTurn;
  searchCalls: number;
  generationCalls: Array<{
    temperature: number;
    stopWhen: unknown;
    granted: number;
  }>;
  grantedMaxSteps: number;
  distinctPairs: string[];
  reconcilations: number;
  stepEvents: number;
};

function stepFinish(stepNumber: number, modelId: string) {
  return {
    stepNumber,
    toolCalls: [],
    usage: {},
    model: { provider: "test", modelId },
    response: { modelId },
  };
}

async function invokeValidate(
  opts: GenerationOpts,
  placements: PlacementSpec[],
) {
  const execute = opts.tools?.validateMove?.execute;
  if (!execute) throw new Error("validateMove.execute missing");
  await execute({ placements });
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  if (typeof Request !== "undefined" && input instanceof Request) return input.url;
  return String(input);
}

function pathnameOf(input: RequestInfo | URL): string {
  const raw = requestUrl(input);
  try {
    return new URL(raw).pathname;
  } catch {
    return raw;
  }
}

function parseBody(init?: RequestInit): Record<string, unknown> {
  if (!init?.body || typeof init.body !== "string") return {};
  try {
    return JSON.parse(init.body) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function findLegal(
  turn: SimTurn,
  placements: PlacementSpec[],
): LegalMoveSpec | undefined {
  const key = placementKey(placements);
  return turn.legalMoves.find((move) => placementKey(move.placements) === key);
}

class FakeDjango {
  turn: SimTurn;
  board: string[];
  rack: string[];
  moveCount: number;
  persistedInvalid = 0;
  terminalPersisted = 0;
  lastAction: "place" | "exchange" | "pass" | null = null;
  lastSource: string | null = null;
  lastCommittedScore: number | null = null;
  rejectNextMove: boolean;
  catalog: CatalogPair[];
  preferenceModelId: string;

  constructor(turn: SimTurn, catalog: CatalogPair[], preferenceModelId: string) {
    this.turn = turn;
    this.board = cloneBoard(turn.board);
    this.rack = [...turn.rack];
    this.moveCount = 4;
    this.rejectNextMove = turn.script === "commit_reject_reprobe_rescue";
    this.catalog = catalog;
    this.preferenceModelId = preferenceModelId;
  }

  snapshot(): { board: string[]; rack: string[] } {
    return { board: cloneBoard(this.board), rack: [...this.rack] };
  }

  handle(input: RequestInfo | URL, init?: RequestInit): Response {
    const path = pathnameOf(input);
    if (path.includes("openrouter.ai") || path.includes("integrate.api.nvidia.com")) {
      throw new Error(`Unexpected provider HTTP: ${path}`);
    }
    if (path.endsWith("/api/catalog/models/")) {
      return jsonResponse(this.catalog);
    }
    const gameMatch = path.match(/^\/api\/game\/([^/]+)\/?(.*)$/);
    if (!gameMatch) {
      throw new Error(`Unexpected backend request: ${path}`);
    }
    const rest = gameMatch[2].replace(/\/$/, "");
    if (rest === "ai-context") {
      return jsonResponse({
        compact_state: this.board.join("\n"),
        ai_state: { ai_rack: this.rack.join(""), human_score: 0, ai_score: 0 },
        is_first_move: this.board.every((row) => row === "..............."),
        ai_model_id: this.preferenceModelId,
        ai_move_max_output_tokens: 2000,
        ai_prompt_id: 1,
        ai_prompt_name: "Initial",
        ai_prompt_text: "SEARCH PROFILE — test",
        ...(this.turn.lexicon_id || this.turn.variant
          ? {
              variant: this.turn.variant ?? "slovak",
              lexicon_id: this.turn.lexicon_id ?? "slovak",
              tile_points: this.turn.tile_points ?? {},
              alphabet: this.turn.alphabet ?? [],
            }
          : {}),
      });
    }
    if (rest === "") {
      return jsonResponse(this.reconciliation());
    }
    if (rest === "ai-playability") {
      return this.playability();
    }
    if (rest === "validate-move") {
      return this.validate(parseBody(init));
    }
    if (rest === "ai-move") {
      return this.aiMove(parseBody(init));
    }
    if (rest === "ai-pass") {
      return this.aiPass(parseBody(init));
    }
    if (rest === "ai-exchange") {
      return this.aiExchange(parseBody(init));
    }
    if (rest === "ai-model") {
      return jsonResponse({ ok: true, ai_model_id: this.preferenceModelId });
    }
    if (rest === "ai-candidates") {
      return this.rankedCandidates();
    }
    throw new Error(`Unexpected backend request: ${path}`);
  }

  reconciliation(): ReconciliationView & { board: string[]; my_rack: string[] } {
    return {
      game_id: "sim-game",
      move_count: this.moveCount,
      status: "active",
      current_turn_slot: 1,
      game_over: false,
      board: this.board,
      my_rack: this.rack,
    };
  }

  playability(): Response {
    if (this.turn.kind === "indeterminate") {
      return jsonResponse({
        status: "indeterminate",
        witness: null,
        exchange_allowed: false,
        exchange_letters: [],
        search: { complete: false, nodes: 9, elapsed_ms: 2000 },
      });
    }
    if (this.turn.kind === "found") {
      const witness = this.turn.witness;
      return jsonResponse({
        status: "found",
        witness: witness
          ? {
              placements: witness.placements,
              words: [witness.word],
              total_score: witness.score,
            }
          : null,
        exchange_allowed: false,
        exchange_letters: [],
        search: { complete: true, nodes: 4, elapsed_ms: 1 },
      });
    }
    return jsonResponse({
      status: "none",
      witness: null,
      exchange_allowed: this.turn.exchangeAllowed,
      exchange_letters: this.turn.exchangeLetters,
      search: { complete: true, nodes: 1, elapsed_ms: 1 },
    });
  }

  rankedCandidates(): Response {
    if (
      this.turn.script === "no_valid_provider_candidate" &&
      this.turn.legalMoves.length > 0
    ) {
      return jsonResponse({
        status: "found",
        candidates: this.turn.legalMoves.map((move) => ({
          placements: move.placements,
          words: [move.word],
          score: move.score,
          tiles_used: move.placements.length,
          leave_value: 0,
        })),
        search: {
          complete: true,
          nodes: 10,
          elapsed_ms: 5,
          unique_placements: this.turn.legalMoves.length,
          candidate_count: this.turn.legalMoves.length,
        },
      });
    }
    return jsonResponse({
      status: "none",
      candidates: [],
      search: {
        complete: true,
        nodes: 1,
        elapsed_ms: 1,
        unique_placements: 0,
        candidate_count: 0,
      },
    });
  }

  validate(body: Record<string, unknown>): Response {
    const placements = Array.isArray(body.placements)
      ? (body.placements as PlacementSpec[])
      : [];
    const legal = findLegal(this.turn, placements);
    if (!legal) {
      return jsonResponse({
        valid: false,
        total_score: 0,
        words: [{ word: "???", valid: false }],
      });
    }
    return jsonResponse({
      valid: true,
      total_score: legal.score,
      words: [{ word: legal.word, valid: true }],
    });
  }

  aiMove(body: Record<string, unknown>): Response {
    const placements = Array.isArray(body.placements)
      ? (body.placements as PlacementSpec[])
      : [];
    const legal = findLegal(this.turn, placements);
    const meta = (body.ai_metadata ?? {}) as Record<string, unknown>;
    if (this.rejectNextMove) {
      this.rejectNextMove = false;
      return jsonResponse({ ok: false, error: "stale candidate" }, 409);
    }
    if (!legal) {
      this.persistedInvalid += 1;
      return jsonResponse({ ok: false, error: "invalid move" }, 400);
    }
    this.board = placeOnBoard(this.board, legal.placements);
    this.rack = remainingRack(this.rack, legal.placements);
    this.moveCount += 1;
    this.terminalPersisted += 1;
    this.lastAction = "place";
    this.lastSource =
      typeof meta.completion_source === "string" ? meta.completion_source : null;
    this.lastCommittedScore = legal.score;
    return jsonResponse({
      ok: true,
      action: "place",
      points: legal.score,
      words: [{ word: legal.word, score: legal.score }],
      state: this.reconciliation(),
    });
  }

  aiPass(body: Record<string, unknown>): Response {
    if (this.turn.kind === "found") {
      return jsonResponse(
        { ok: false, code: "legal_scoring_move_exists", error: "legal move exists" },
        409,
      );
    }
    if (this.turn.kind === "indeterminate") {
      return jsonResponse(
        { ok: false, code: "playability_unknown", error: "unknown" },
        409,
      );
    }
    if (this.turn.exchangeAllowed) {
      return jsonResponse(
        { ok: false, code: "exchange_required", error: "exchange required" },
        409,
      );
    }
    const meta = (body.ai_metadata ?? {}) as Record<string, unknown>;
    this.moveCount += 1;
    this.terminalPersisted += 1;
    this.lastAction = "pass";
    this.lastSource =
      typeof meta.completion_source === "string" ? meta.completion_source : null;
    return jsonResponse({
      ok: true,
      action: "pass",
      state: this.reconciliation(),
    });
  }

  aiExchange(body: Record<string, unknown>): Response {
    if (this.turn.kind === "found") {
      return jsonResponse(
        { ok: false, code: "legal_scoring_move_exists", error: "legal move exists" },
        409,
      );
    }
    if (this.turn.kind === "indeterminate") {
      return jsonResponse(
        { ok: false, code: "playability_unknown", error: "unknown" },
        409,
      );
    }
    if (!this.turn.exchangeAllowed) {
      return jsonResponse(
        { ok: false, code: "exchange_unavailable", error: "cannot exchange" },
        409,
      );
    }
    const meta = (body.ai_metadata ?? {}) as Record<string, unknown>;
    this.rack = [...this.turn.afterRack];
    this.moveCount += 1;
    this.terminalPersisted += 1;
    this.lastAction = "exchange";
    this.lastSource =
      typeof meta.completion_source === "string" ? meta.completion_source : null;
    return jsonResponse({
      ok: true,
      action: "exchange",
      state: this.reconciliation(),
    });
  }
}

async function runScriptedGeneration(
  engine: EngineState,
  opts: GenerationOpts,
): Promise<{ text: string; steps: ReturnType<typeof stepFinish>[] }> {
  const temperature = opts.temperature ?? 0;
  const stopWhen = opts.stopWhen;
  engine.generationCalls.push({
    temperature,
    stopWhen,
    granted: engine.grantedMaxSteps,
  });
  const cap = typeof stopWhen === "number" ? stopWhen : TURN_MAX_STEPS;
  const finish = async (count: number, extra?: () => Promise<void>) => {
    const steps = [];
    for (let i = 0; i < count; i += 1) {
      const step = stepFinish(i, "sim");
      opts.onStepFinish?.(step);
      engine.stepEvents += 1;
      steps.push(step);
    }
    if (extra) await extra();
    return { text: "{}", steps };
  };

  if (temperature === 0) {
    if (engine.turn.script === "timeout_witness_rescue") {
      throw new DOMException("Timeout", "AbortError");
    }
    if (engine.turn.script === "invalid_then_repair" && engine.turn.witness) {
      await invokeValidate(opts, engine.turn.witness.placements);
      return finish(Math.min(2, cap));
    }
    return finish(0);
  }

  engine.searchCalls += 1;
  const script = engine.turn.script;

  if (script === "no_valid_provider_candidate") {
    const signal = opts.abortSignal;
    await new Promise<never>((_, reject) => {
      const fail = () => reject(new DOMException("Timeout", "AbortError"));
      if (!signal) {
        reject(new Error("abortSignal missing"));
        return;
      }
      if (signal.aborted) {
        fail();
        return;
      }
      signal.addEventListener("abort", fail, { once: true });
    });
  }

  if (script === "retryable_429_fallback" && engine.searchCalls === 1) {
    throw Object.assign(new Error("rate limit"), { statusCode: 429 });
  }
  if (
    script === "retryable_no_endpoints_fallback" &&
    engine.searchCalls === 1
  ) {
    throw Object.assign(
      new Error("No endpoints found for stealth/example:free"),
      { name: "AI_APICallError", statusCode: 404 },
    );
  }
  if (script === "timeout_witness_rescue") {
    throw new DOMException("Timeout", "AbortError");
  }
  if (script === "invalid_then_repair") {
    await invokeValidate(opts, engine.turn.invalidPlacement);
    return finish(1);
  }
  if (script === "highest_score_retained") {
    await invokeValidate(opts, engine.turn.legalMoves[0].placements);
    await invokeValidate(opts, engine.turn.legalMoves[1].placements);
    return finish(2);
  }
  if (
    script === "genuine_exchange" ||
    script === "genuine_pass" ||
    script === "indeterminate_probe"
  ) {
    return finish(1);
  }
  await invokeValidate(opts, engine.turn.legalMoves[0].placements);
  if (script === "valid_then_pass_text") {
    const steps = (await finish(1)).steps;
    return { text: JSON.stringify({ action: "pass" }), steps };
  }
  if (script === "malformed_output") {
    const steps = (await finish(1)).steps;
    return { text: "not-json", steps };
  }
  return finish(1);
}

async function runTurn(
  turn: SimTurn,
  rival: CatalogPair,
  catalog: CatalogPair[],
  routeBody?: Record<string, unknown>,
): Promise<{
  django: FakeDjango;
  engine: EngineState;
  stopReason: string;
  lastAction: string | undefined;
  lastSource: string | null | undefined;
  posts: number;
  reconcilations: number;
  providerRequestsUsed: number;
}> {
  const django = new FakeDjango(turn, catalog, rival.model_id);
  const engine: EngineState = {
    turn,
    searchCalls: 0,
    generationCalls: [],
    grantedMaxSteps: TURN_MAX_STEPS,
    distinctPairs: [],
    reconcilations: 0,
    stepEvents: 0,
  };

  harness.generateText.mockImplementation((opts: GenerationOpts) =>
    runScriptedGeneration(engine, opts),
  );

  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      return django.handle(input, init);
    }),
  );

  const queue = buildFallbackQueue(rival.model_id, catalog);
  const result = await orchestrateFallbackTurn({
    queue,
    turnStartedAtMs: 0,
    aiTimeoutSeconds: 60,
    maxStepsTotal: 30,
    now: () => 1_000,
    anchor: { gameId: "sim-game", moveCount: 4, aiSlot: 1 },
    fetchGameState: async () => {
      engine.reconcilations += 1;
      const latest = django.reconciliation();
      return {
        game_id: latest.game_id,
        move_count: latest.move_count,
        status: latest.status,
        current_turn_slot: latest.current_turn_slot,
        game_over: latest.game_over,
      };
    },
    runStream: async ({ pair, timeoutSeconds, maxStepsRemaining }) => {
      engine.distinctPairs.push(`${pair.provider}:${pair.model_id}`);
      engine.grantedMaxSteps = maxStepsRemaining;
      const req = new NextRequest("http://localhost/api/ai/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          game_id: "sim-game",
          token: "sim-token",
          model_id: rival.model_id,
          runtime_model_id: pair.model_id,
          timeout: timeoutSeconds,
          max_steps: maxStepsRemaining,
          ...routeBody,
        }),
      });
      const response = await POST(req);
      if (!(response.headers.get("content-type") ?? "").includes("text/event-stream")) {
        throw new Error("expected SSE from move route");
      }
      return consumeAIStream(response, {
        onCandidate: () => {},
        onStatus: () => {},
      });
    },
  });

  const done = result.lastTerminal?.kind === "done" ? result.lastTerminal.data : null;
  return {
    django,
    engine,
    stopReason: result.stopReason,
    lastAction: typeof done?.action === "string" ? done.action : undefined,
    lastSource:
      typeof done?.completion_source === "string"
        ? done.completion_source
        : django.lastSource,
    posts: result.posts.length,
    reconcilations: engine.reconcilations,
    providerRequestsUsed: result.providerRequestsUsed,
  };
}

describe("playable-free-rivals 300-turn causal simulation", () => {
  beforeEach(() => {
    harness.generateText.mockReset();
    vi.stubEnv("OPENROUTER_API_KEY", "test-openrouter-key");
    vi.stubEnv("NVIDIA_API_KEY", "test-nvidia-key");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.useRealTimers();
  });

  it("pins anti-pass recovery across five bootstrap rivals in under 10s", async () => {
    const started = Date.now();
    const games = buildReplayGames();
    expect(games).toHaveLength(
      DATA.bootstrap_rivals.length * DATA.games_per_rival,
    );

    let foundTurns = 0;
    let exchangeTurns = 0;
    let passTurns = 0;
    let avoidableNonScoring = 0;
    let foundPlaced = 0;
    let genuineOk = 0;
    let persistedInvalid = 0;
    let highestRetained = 0;
    let highestTotal = 0;
    let boardRackTransitions = 0;
    let stepCapViolations = 0;
    let pairCapViolations = 0;
    let reconcileViolations = 0;

    for (const game of games) {
      for (const turn of game.turns) {
        const beforeBoard = turn.board.join("|");
        const beforeRack = turn.rack.join("");
        const outcome = await runTurn(turn, game.rival, DATA.bootstrap_rivals);
        const after = outcome.django.snapshot();
        boardRackTransitions += 2;
        expect(beforeBoard).toBe(turn.board.join("|"));
        expect(beforeRack).toBe(turn.rack.join(""));
        expect(after.board.join("|")).toBe(turn.afterBoard.join("|"));
        expect(after.rack.join("")).toBe(turn.afterRack.join(""));

        persistedInvalid += outcome.django.persistedInvalid;

        if (outcome.posts > 3) pairCapViolations += 1;
        if (new Set(outcome.engine.distinctPairs).size > 3) pairCapViolations += 1;
        if (outcome.posts > 1 && outcome.reconcilations !== outcome.posts - 1) {
          reconcileViolations += 1;
        }
        if (outcome.posts > 1 && outcome.reconcilations < 1) {
          reconcileViolations += 1;
        }

        for (const call of outcome.engine.generationCalls) {
          const cap = typeof call.stopWhen === "number" ? call.stopWhen : -1;
          if (call.temperature === 0) {
            if (cap > REPAIR_RESERVE) stepCapViolations += 1;
          } else if (cap > call.granted - REPAIR_RESERVE) {
            stepCapViolations += 1;
          }
          if (cap > call.granted) stepCapViolations += 1;
        }

        if (turn.kind === "found") {
          foundTurns += 1;
          if (outcome.lastAction === "place") foundPlaced += 1;
          if (outcome.lastAction === "pass" || outcome.lastAction === "exchange") {
            avoidableNonScoring += 1;
          }
          if (turn.script === "highest_score_retained") {
            highestTotal += 1;
            if (outcome.django.lastCommittedScore === DATA.tiles.rates.score) {
              highestRetained += 1;
            }
          }
        } else if (turn.kind === "exchange") {
          exchangeTurns += 1;
          if (
            outcome.lastAction === "exchange" &&
            outcome.lastSource === "genuine_no_move_exchange"
          ) {
            genuineOk += 1;
          }
        } else if (turn.kind === "pass") {
          passTurns += 1;
          if (
            outcome.lastAction === "pass" &&
            outcome.lastSource === "genuine_no_move_pass"
          ) {
            genuineOk += 1;
          }
        }
      }
    }

    const elapsed = Date.now() - started;
    expect(foundTurns).toBe(270);
    expect(exchangeTurns).toBe(15);
    expect(passTurns).toBe(15);
    expect(foundTurns + exchangeTurns + passTurns).toBe(300);
    expect(avoidableNonScoring).toBe(0);
    expect(foundPlaced).toBe(270);
    expect(highestTotal).toBeGreaterThan(0);
    expect(highestRetained).toBe(highestTotal);
    expect(genuineOk).toBe(30);
    expect(persistedInvalid).toBe(0);
    expect(stepCapViolations).toBe(0);
    expect(pairCapViolations).toBe(0);
    expect(reconcileViolations).toBe(0);
    expect(boardRackTransitions).toBe(600);
    expect(elapsed).toBeLessThan(10_000);
  }, 15_000);

  it("probes indeterminate with zero backend terminal persistence", async () => {
    const turn = buildIndeterminateTurn("indeterminate-0");
    const rival = DATA.bootstrap_rivals[0];
    const outcome = await runTurn(turn, rival, DATA.bootstrap_rivals);
    expect(outcome.lastAction).toBeUndefined();
    expect(outcome.django.terminalPersisted).toBe(0);
    expect(outcome.django.lastAction).toBeNull();
    expect(outcome.django.snapshot().board.join("|")).toBe(turn.board.join("|"));
    expect(outcome.django.snapshot().rack.join("")).toBe(turn.rack.join(""));
    expect(outcome.stopReason).not.toBe("done");
  });

  it("slovak found rack does not complete with genuine_no_move_pass", async () => {
    const auto: LegalMoveSpec = {
      placements: [
        { row: 7, col: 5, letter: "A" },
        { row: 7, col: 6, letter: "U" },
        { row: 7, col: 7, letter: "T" },
        { row: 7, col: 8, letter: "O" },
      ],
      word: "AUTO",
      score: 12,
    };
    const hra: LegalMoveSpec = {
      placements: [
        { row: 7, col: 6, letter: "H" },
        { row: 7, col: 7, letter: "R" },
        { row: 7, col: 8, letter: "A" },
      ],
      word: "HRA",
      score: 12,
    };
    const turn = buildFoundTurn("slovak-found-0", "valid_placement", {
      found_rack: ["A", "U", "T", "O", "H", "R", "Á"],
      rate: auto,
      rates: hra,
      invalid_placement: [{ row: 0, col: 0, letter: "X" }],
      exchange_rack: [],
      exchange_after_rack: [],
      pass_rack: [],
    });
    turn.variant = "slovak";
    turn.lexicon_id = "slovak";
    turn.tile_points = { A: 1, U: 3, T: 1, O: 1, H: 4, R: 1, Á: 4, X: 10, "?": 0 };
    turn.alphabet = ["A", "Á", "H", "O", "R", "T", "U", "X"];

    const outcome = await runTurn(
      turn,
      DATA.bootstrap_rivals[0],
      DATA.bootstrap_rivals,
    );

    expect(turn.legalMoves.length).toBeGreaterThan(0);
    expect(outcome.lastAction).toBe("place");
    expect(outcome.lastSource).not.toBe("genuine_no_move_pass");
    expect(outcome.lastSource).not.toBe("genuine_no_move_exchange");
    expect([
      "provider_candidate",
      "repair_candidate",
      "backend_witness_rescue",
      "backend_ranked_candidate",
    ]).toContain(outcome.lastSource);
  });

  it("reconciles once and advances to rival 2 after a no-endpoints provider 404", async () => {
    const turn = buildFoundTurn(
      "no-endpoints-fallback-0",
      "retryable_no_endpoints_fallback",
    );
    const outcome = await runTurn(
      turn,
      DATA.bootstrap_rivals[0],
      DATA.bootstrap_rivals,
    );

    expect(outcome.stopReason).toBe("done");
    expect(outcome.posts).toBe(2);
    expect(outcome.reconcilations).toBe(1);
    expect(outcome.engine.searchCalls).toBe(2);
    expect(outcome.engine.distinctPairs).toHaveLength(2);
    expect(new Set(outcome.engine.distinctPairs).size).toBe(2);
    expect(outcome.django.terminalPersisted).toBe(1);
    expect(outcome.django.persistedInvalid).toBe(0);
    expect(outcome.lastAction).toBe("place");
  });

  it("finalizes a no-progress model from the ranked candidate before the hard timeout", async () => {
    vi.useFakeTimers();
    const turn = buildFoundTurn(
      "no-valid-provider-0",
      "no_valid_provider_candidate",
    );
    const pending = runTurn(
      turn,
      DATA.bootstrap_rivals[0],
      DATA.bootstrap_rivals,
      { no_provider_progress_deadline: 3 },
    );
    for (let i = 0; i < 100 && harness.generateText.mock.calls.length === 0; i += 1) {
      await Promise.resolve();
    }
    expect(harness.generateText.mock.calls.length).toBeGreaterThan(0);
    await vi.advanceTimersByTimeAsync(3_000);
    await Promise.resolve();
    await Promise.resolve();
    const outcome = await pending;

    expect(outcome.lastAction).toBe("place");
    expect(outcome.lastSource).toBe("backend_ranked_candidate");
    expect(outcome.lastAction).not.toBe("pass");
    expect(outcome.lastAction).not.toBe("exchange");
    expect(outcome.django.persistedInvalid).toBe(0);
    expect(outcome.django.terminalPersisted).toBe(1);
    expect(outcome.posts).toBeLessThanOrEqual(3);
    expect(new Set(outcome.engine.distinctPairs).size).toBeLessThanOrEqual(3);
    expect(outcome.engine.distinctPairs.length).toBeLessThanOrEqual(3);
    expect(outcome.django.snapshot().board.join("|")).toBe(turn.afterBoard.join("|"));
  });
});
