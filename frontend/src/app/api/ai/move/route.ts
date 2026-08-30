/**
 * AI Move Generation API Route — SSE Streaming
 *
 * Streams real-time progress events to the frontend while the AI agent
 * searches for a backend-validated placement. Free-form model text has no
 * authority over pass, exchange, or place; only tracked validateMove results
 * and the Slice-1 playability probe may terminate the turn.
 *
 * SSE Event Flow:
 *   thinking    → AI started, timeout set
 *   tool_use    → AI called validateMove / finishMove
 *   tool_result → Tool returned a result
 *   candidate   → Valid move candidate found (word, score, isBest)
 *   done        → Final move applied (or genuine no-move exchange/pass)
 *   error       → Something went wrong; turn unchanged
 */

import { NextRequest } from "next/server";
import { generateText, tool, stepCountIs } from "ai";
import { z } from "zod";
import {
  findCatalogPair,
  revalidateRuntimePair,
} from "@/lib/model-catalog";
import {
  getLanguageRuntime,
  isLegalBackendTerminal,
  normalizeProviderError,
  parseCatalogModelRows,
  type ProviderRequestTracker,
} from "@/lib/ai-runtimes";
import {
  MOVE_PROMPT_VERSION,
  composeMoveSystemPrompt,
  buildMoveUserPrompt,
  movePromptSpecFromContext,
} from "@/lib/prompts";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const DEFAULT_TIMEOUT_S = 120;
const DEFAULT_MAX_STEPS = 50;
const MIN_TIMEOUT_S = 1;
const MIN_STEPS = 5;
const MAX_STEPS = 100;
const DEFAULT_MAX_OUTPUT_TOKENS = 10000;
const MIN_MAX_OUTPUT_TOKENS = 2000;
const MAX_MAX_OUTPUT_TOKENS = 64000;
const AUTO_FINALIZE_GRACE_MS = 2500;
const AUTO_FINALIZE_VALID_CAP = 4;
const EXTENDED_AUTO_FINALIZE_GRACE_MS = 6000;
const EXTENDED_AUTO_FINALIZE_VALID_CAP = 7;
const REPAIR_RESERVE_STEPS = 2;
const REPAIR_MIN_REMAINING_SECONDS = 2;
const SEARCH_TEMPERATURE = 0.15;
const REPAIR_TEMPERATURE = 0;

type CompletionSource =
  | "provider_candidate"
  | "backend_ranked_candidate"
  | "repair_candidate"
  | "backend_witness_rescue"
  | "genuine_no_move_exchange"
  | "genuine_no_move_pass";
type AbortReason = "timeout" | "auto_finalize" | "finish";

function summarizeBackendBody(body: string) {
  return body.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 220);
}

async function parseBackendJson(res: Response, path: string) {
  const raw = await res.text();
  try {
    return JSON.parse(raw);
  } catch {
    const preview = summarizeBackendBody(raw);
    throw new Error(
      preview
        ? `Backend ${path} returned non-JSON (${res.status}): ${preview}`
        : `Backend ${path} returned non-JSON (${res.status})`,
    );
  }
}

async function backendRequest(
  path: string,
  token: string,
  init?: { method?: "GET" | "POST" | "PATCH"; body?: unknown },
) {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: init?.method ?? "GET",
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  return parseBackendJson(res, path);
}

async function backendPost(path: string, body: unknown, token: string) {
  return backendRequest(path, token, { method: "POST", body });
}

async function backendGet(path: string, token: string) {
  return backendRequest(path, token);
}

async function backendPatch(path: string, body: unknown, token: string) {
  return backendRequest(path, token, { method: "PATCH", body });
}

const placementSchema = z.object({
  row: z.number().min(0).max(14).describe("Row index (0-14)"),
  col: z.number().min(0).max(14).describe("Column index (0-14)"),
  letter: z
    .string()
    .length(1)
    .describe("Tile letter (one Unicode letter) or ? for blank"),
  blank_as: z
    .string()
    .length(1)
    .optional()
    .describe("If letter is ?, the Unicode letter it represents"),
});

type PlacementData = {
  row: number;
  col: number;
  letter: string;
  blank_as?: string;
};

type Candidate = {
  word: string;
  score: number;
  valid: boolean;
  allWords: string[];
  placements: PlacementData[];
  timestamp: number;
};

type UsageLike = {
  inputTokens?: number | { total?: number; noCache?: number; cacheRead?: number; cacheWrite?: number };
  inputTokenDetails?: { noCacheTokens?: number; cacheReadTokens?: number; cacheWriteTokens?: number };
  outputTokens?: number | { total?: number; text?: number; reasoning?: number };
  outputTokenDetails?: { textTokens?: number; reasoningTokens?: number };
  totalTokens?: number;
  raw?: unknown;
};

type PlayabilityPayload = {
  status?: unknown;
  witness?: unknown;
  exchange_allowed?: unknown;
  exchange_letters?: unknown;
  ok?: unknown;
  code?: unknown;
  error?: unknown;
};

type PlacementChoice = {
  word: string;
  score: number;
  allWords: string[];
  placements: PlacementData[];
  source: "provider_candidate" | "backend_ranked_candidate";
  backendOrder: number | null;
  providerOrder: number | null;
};

function sseEvent(data: Record<string, unknown>): string {
  return `data: ${JSON.stringify(data)}\n\n`;
}

async function fetchCatalogModelRows() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/catalog/models/`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data: unknown = await res.json();
    if (!Array.isArray(data)) return null;
    return parseCatalogModelRows(data);
  } catch {
    return null;
  }
}

function normalizeUsage(usage?: UsageLike | null) {
  if (!usage) return null;

  const inputTokenDetails = usage.inputTokenDetails;
  const outputTokenDetails = usage.outputTokenDetails;
  const nestedInput =
    typeof usage.inputTokens === "object" && usage.inputTokens !== null
      ? usage.inputTokens
      : null;
  const nestedOutput =
    typeof usage.outputTokens === "object" && usage.outputTokens !== null
      ? usage.outputTokens
      : null;

  const inputTokens =
    nestedInput?.total ??
    (typeof usage.inputTokens === "number" ? usage.inputTokens : undefined) ??
    0;
  const outputTokens =
    nestedOutput?.total ??
    (typeof usage.outputTokens === "number" ? usage.outputTokens : undefined) ??
    0;
  const cacheReadTokens =
    nestedInput?.cacheRead ?? inputTokenDetails?.cacheReadTokens ?? 0;
  const cacheWriteTokens =
    nestedInput?.cacheWrite ?? inputTokenDetails?.cacheWriteTokens ?? 0;
  const noCacheTokens =
    nestedInput?.noCache ??
    inputTokenDetails?.noCacheTokens ??
    Math.max(inputTokens - cacheReadTokens - cacheWriteTokens, 0);
  const textTokens =
    nestedOutput?.text ?? outputTokenDetails?.textTokens ?? outputTokens;
  const reasoningTokens =
    nestedOutput?.reasoning ?? outputTokenDetails?.reasoningTokens ?? 0;

  return {
    inputTokens,
    inputTokenDetails: {
      noCacheTokens,
      cacheReadTokens,
      cacheWriteTokens,
    },
    outputTokens,
    outputTokenDetails: {
      textTokens,
      reasoningTokens,
    },
    totalTokens: usage.totalTokens ?? inputTokens + outputTokens,
    raw: usage.raw ?? null,
  };
}

function mergeUsage(
  base: ReturnType<typeof normalizeUsage>,
  extra: ReturnType<typeof normalizeUsage>,
) {
  if (!base) return extra;
  if (!extra) return base;

  return {
    inputTokens: base.inputTokens + extra.inputTokens,
    inputTokenDetails: {
      noCacheTokens:
        base.inputTokenDetails.noCacheTokens + extra.inputTokenDetails.noCacheTokens,
      cacheReadTokens:
        base.inputTokenDetails.cacheReadTokens + extra.inputTokenDetails.cacheReadTokens,
      cacheWriteTokens:
        base.inputTokenDetails.cacheWriteTokens + extra.inputTokenDetails.cacheWriteTokens,
    },
    outputTokens: base.outputTokens + extra.outputTokens,
    outputTokenDetails: {
      textTokens:
        base.outputTokenDetails.textTokens + extra.outputTokenDetails.textTokens,
      reasoningTokens:
        base.outputTokenDetails.reasoningTokens + extra.outputTokenDetails.reasoningTokens,
    },
    totalTokens: base.totalTokens + extra.totalTokens,
    raw: base.raw ?? extra.raw ?? null,
  };
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function normalizePlacementData(value: unknown): PlacementData | null {
  if (!isRecord(value)) return null;
  const row = typeof value.row === "number" ? value.row : null;
  const col = typeof value.col === "number" ? value.col : null;
  const letter =
    typeof value.letter === "string"
      ? value.letter.normalize("NFC").trim().toUpperCase()
      : null;
  const blankAs =
    typeof value.blank_as === "string"
      ? value.blank_as.normalize("NFC").trim().toUpperCase()
      : typeof value.blankAs === "string"
        ? value.blankAs.normalize("NFC").trim().toUpperCase()
        : null;

  if (
    row === null ||
    col === null ||
    !Number.isInteger(row) ||
    !Number.isInteger(col) ||
    row < 0 ||
    row > 14 ||
    col < 0 ||
    col > 14 ||
    !letter ||
    !/^[\p{L}?]$/u.test(letter)
  ) {
    return null;
  }

  if (letter === "?" && (!blankAs || !/^\p{L}$/u.test(blankAs))) return null;
  if (letter !== "?" && blankAs !== null) return null;

  return {
    row,
    col,
    letter,
    ...(blankAs && blankAs.length === 1 ? { blank_as: blankAs } : {}),
  };
}

function normalizePlacementArray(value: unknown): PlacementData[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => normalizePlacementData(item))
    .filter((item): item is PlacementData => item !== null);
}

function placementKey(placements: PlacementData[]): string {
  return JSON.stringify(
    [...placements]
      .sort(
        (left, right) =>
          left.row - right.row ||
          left.col - right.col ||
          left.letter.localeCompare(right.letter) ||
          (left.blank_as ?? "").localeCompare(right.blank_as ?? ""),
      )
      .map((placement) => [
        placement.row,
        placement.col,
        placement.letter,
        placement.blank_as ?? "",
      ]),
  );
}

function normalizeRankedChoices(value: unknown): PlacementChoice[] {
  if (!isRecord(value) || value.status !== "found" || !Array.isArray(value.candidates)) {
    return [];
  }
  const seen = new Set<string>();
  const choices: PlacementChoice[] = [];
  for (const [backendOrder, raw] of value.candidates.entries()) {
    if (!isRecord(raw) || !Array.isArray(raw.placements)) continue;
    const placements = normalizePlacementArray(raw.placements);
    if (
      placements.length === 0 ||
      placements.length > 7 ||
      placements.length !== raw.placements.length ||
      typeof raw.score !== "number" ||
      !Number.isInteger(raw.score) ||
      raw.score <= 0
    ) {
      continue;
    }
    const key = placementKey(placements);
    if (seen.has(key)) continue;
    seen.add(key);
    const allWords = Array.isArray(raw.words)
      ? raw.words.filter((word): word is string => typeof word === "string")
      : [];
    choices.push({
      word: allWords[0] ?? "???",
      score: raw.score,
      allWords,
      placements,
      source: "backend_ranked_candidate",
      backendOrder,
      providerOrder: null,
    });
  }
  return choices;
}

function mergePlacementChoices(
  backendChoices: PlacementChoice[],
  providerCandidates: Candidate[],
): PlacementChoice[] {
  const merged = [...backendChoices];
  const seen = new Set(backendChoices.map((choice) => placementKey(choice.placements)));
  for (const [providerOrder, candidate] of providerCandidates.entries()) {
    if (!candidate.valid) continue;
    const key = placementKey(candidate.placements);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push({
      word: candidate.word,
      score: candidate.score,
      allWords: candidate.allWords,
      placements: candidate.placements,
      source: "provider_candidate",
      backendOrder: null,
      providerOrder,
    });
  }
  return merged.sort((left, right) => {
    if (left.score !== right.score) return right.score - left.score;
    if (left.backendOrder !== null && right.backendOrder === null) return -1;
    if (left.backendOrder === null && right.backendOrder !== null) return 1;
    if (left.backendOrder !== null && right.backendOrder !== null) {
      return left.backendOrder - right.backendOrder;
    }
    const providerOrder = (left.providerOrder ?? 0) - (right.providerOrder ?? 0);
    return providerOrder || placementKey(left.placements).localeCompare(placementKey(right.placements));
  });
}

function stepCountFromResult(result: { steps?: unknown[] } | null | undefined): number {
  return Array.isArray(result?.steps) ? result.steps.length : 0;
}

function usageForMetadata(usage: ReturnType<typeof normalizeUsage>) {
  if (!usage) return undefined;
  return {
    inputTokens: usage.inputTokens,
    outputTokens: usage.outputTokens,
    totalTokens: usage.totalTokens,
  };
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { game_id, token, model_id, runtime_model_id, timeout } = body as {
    game_id: string;
    token: string;
    model_id?: string;
    runtime_model_id?: string;
    timeout?: number;
    max_steps?: number;
  };

  const requestedTimeout =
    typeof timeout === "number" && Number.isFinite(timeout)
      ? Math.floor(timeout)
      : DEFAULT_TIMEOUT_S;
  const timeoutS = clampNumber(requestedTimeout, MIN_TIMEOUT_S, 600);
  const requestedMaxSteps =
    typeof body.max_steps === "number" && Number.isFinite(body.max_steps)
      ? Math.floor(body.max_steps)
      : DEFAULT_MAX_STEPS;
  const maxSteps = Math.max(
    MIN_STEPS,
    Math.min(requestedMaxSteps, MAX_STEPS),
  );
  const searchStepCap = maxSteps - REPAIR_RESERVE_STEPS;
  const startTime = Date.now();
  const requestedModelId = typeof model_id === "string" && model_id ? model_id : null;
  const requestedRuntimeModelId =
    typeof runtime_model_id === "string" && runtime_model_id
      ? runtime_model_id
      : requestedModelId;

  const stream = new ReadableStream({
    async start(controller) {
      const encoder = new TextEncoder();
      let streamClosed = false;

      function emit(data: Record<string, unknown>) {
        if (streamClosed) return;
        try {
          controller.enqueue(encoder.encode(sseEvent(data)));
        } catch {
          // stream may have been closed by the client
        }
      }

      function closeStream() {
        if (streamClosed) return;
        streamClosed = true;
        try {
          controller.close();
        } catch {
          // already closed
        }
      }

      let providerPath = "";
      let runtimeModelId = requestedRuntimeModelId || requestedModelId || "";

      const candidates: Candidate[] = [];
      let bestScore = -1;
      let autoFinalized = false;
      let autoFinalizeTimer: ReturnType<typeof setTimeout> | null = null;
      const abortController = new AbortController();
      let abortReason: AbortReason | null = null;
      let autoFinalizeGraceMs = AUTO_FINALIZE_GRACE_MS;
      let autoFinalizeValidCap = AUTO_FINALIZE_VALID_CAP;
      let accumulatedUsage: ReturnType<typeof normalizeUsage> = null;
      let completedStepCount = 0;
      let lastResponseModelId: string | undefined;
      let repairAttempted = false;
      let probeStatus: string | null = null;
      let completionSource: CompletionSource | null = null;
      let terminalCause = "";
      let recordedProviderRequests = 0;
      let runtimeTracker: ProviderRequestTracker | null = null;
      let rankedCandidatePromise: Promise<PlacementChoice[]> | null = null;

      function fetchRankedCandidatesOnce(): Promise<PlacementChoice[]> {
        if (rankedCandidatePromise === null) {
          rankedCandidatePromise = backendGet(
            `/api/game/${game_id}/ai-candidates/`,
            token,
          )
            .then((payload) => normalizeRankedChoices(payload))
            .catch(() => []);
        }
        return rankedCandidatePromise;
      }

      async function rankedAndProviderChoices(): Promise<PlacementChoice[]> {
        const backendChoices = await fetchRankedCandidatesOnce();
        return mergePlacementChoices(backendChoices, candidates);
      }

      function abortGeneration(reason: AbortReason) {
        if (abortReason === null) abortReason = reason;
        abortController.abort();
      }

      function clearAutoFinalizeTimer() {
        if (autoFinalizeTimer) {
          clearTimeout(autoFinalizeTimer);
          autoFinalizeTimer = null;
        }
      }

      function remainingSeconds(): number {
        return timeoutS - (Date.now() - startTime) / 1000;
      }

      function trackCandidate(
        result: Record<string, unknown>,
        placements: PlacementData[],
      ) {
        const score = (result.total_score as number) ?? 0;
        const words = (result.words as Array<{ word: string; valid: boolean }>) ?? [];
        const allWords = words.map((w) => w.word);
        const allValid = result.valid === true && words.every((w) => w.valid);
        const primaryWord = allWords[0] ?? "???";
        const isBest = allValid && score > bestScore;

        if (isBest) bestScore = score;

        const candidate: Candidate = {
          word: primaryWord,
          score,
          valid: allValid,
          allWords,
          placements,
          timestamp: Date.now() - startTime,
        };

        if (allValid) {
          candidates.push(candidate);

          const validCount = candidates.length;
          const best = getBestCandidate();

          if (best) {
            clearAutoFinalizeTimer();

            emit({
              type: "thinking",
              status: "candidate_found",
              message: `Found ${best.word} for ${best.score} points. Checking a few last alternatives...`,
              auto_finalize_ms: autoFinalizeGraceMs,
              valid_candidates: validCount,
              provider_path: providerPath,
              runtime_model: runtimeModelId,
            });

            if (validCount >= autoFinalizeValidCap) {
              autoFinalized = true;
              abortGeneration("auto_finalize");
            } else {
              autoFinalizeTimer = setTimeout(() => {
                autoFinalized = true;
                abortGeneration("auto_finalize");
              }, autoFinalizeGraceMs);
            }
          }
        }

        emit({
          type: "candidate",
          word: primaryWord,
          score,
          valid: allValid,
          isBest: isBest,
          allWords,
          timestamp: candidate.timestamp,
        });
      }

      function getBestCandidate(): Candidate | null {
        const valid = candidates.filter((c) => c.valid);
        if (valid.length === 0) return null;
        valid.sort((a, b) => b.score - a.score);
        return valid[0];
      }

      function noteGenerationResult(result: { steps?: unknown[] } | null | undefined) {
        const fromResult = stepCountFromResult(result);
        if (fromResult > 0) {
          recordedProviderRequests += fromResult;
        }
      }

      function attemptProviderRequests(): number {
        return Math.max(
          runtimeTracker?.snapshot().provider_requests ?? 0,
          recordedProviderRequests,
          completedStepCount,
        );
      }

      function retryAfterFields(): Record<string, number> {
        const retryAfterSeconds = runtimeTracker?.snapshot().retry_after_seconds;
        return retryAfterSeconds === undefined
          ? {}
          : { retry_after_seconds: retryAfterSeconds };
      }

      let sessionModelId: string | null = null;
      let promptContext: {
        ai_prompt_id?: unknown;
        ai_prompt_name?: unknown;
      } | null = null;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let aiResult: any = null;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let repairResult: any = null;
      let userPrompt = "";
      let languageModel: Awaited<ReturnType<typeof getLanguageRuntime>>["model"] | null =
        null;
      let forceValidateMoveConfig: {
        activeTools: Array<"validateMove" | "finishMove">;
        toolChoice: { type: "tool"; toolName: "validateMove" };
      } | null = null;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let runGenerationImpl: ((model: any, args: any) => Promise<any>) | null = null;
      let terminalSent = false;
      const BOUNDED_INTERNAL_ERROR = "The AI turn could not be completed.";

      function runtimeFields() {
        const used = attemptProviderRequests();
        return {
          provider_path: providerPath,
          runtime_model: runtimeModelId,
          provider_requests_used: used,
          turn_provider_requests_used: used,
          ...retryAfterFields(),
        };
      }

      function boundedAiMetadata(source: CompletionSource) {
        const used = attemptProviderRequests();
        const meta: Record<string, unknown> = {
          prompt_version: MOVE_PROMPT_VERSION,
          requested_model_id: requestedModelId,
          runtime_provider: providerPath,
          runtime_model_id: runtimeModelId,
          completion_source: source,
          repair_attempted: repairAttempted,
          terminal_cause: terminalCause,
          provider_requests_used: used,
          turn_provider_requests: used,
          valid_candidate_count: candidates.filter((c) => c.valid).length,
        };
        Object.assign(meta, retryAfterFields());
        if (typeof promptContext?.ai_prompt_id === "number") {
          meta.prompt_id = promptContext.ai_prompt_id;
        }
        if (typeof promptContext?.ai_prompt_name === "string") {
          meta.prompt_name = promptContext.ai_prompt_name;
        }
        if (probeStatus) meta.probe_status = probeStatus;
        const usage = usageForMetadata(
          normalizeUsage(
            (aiResult?.totalUsage as UsageLike | undefined) ??
              (aiResult?.usage as UsageLike | undefined) ??
              null,
          ) ?? accumulatedUsage,
        );
        if (usage) meta.usage = usage;
        return meta;
      }

      function emitDone(
        action: "place" | "pass" | "exchange",
        payload: Record<string, unknown>,
        extra: Record<string, unknown> = {},
      ) {
        terminalSent = true;
        emit({
          type: "done",
          action,
          ...payload,
          requested_model: requestedModelId,
          session_model: sessionModelId,
          response_model: aiResult?.response?.modelId ?? lastResponseModelId,
          elapsed_ms: Date.now() - startTime,
          candidates_found: candidates.length,
          timed_out: abortReason === "timeout",
          auto_finalized: autoFinalized,
          completion_source: completionSource,
          probe_status: probeStatus,
          repair_attempted: repairAttempted,
          terminal_cause: terminalCause,
          ...runtimeFields(),
          ...extra,
        });
      }

      function emitTerminalError(
        message: string,
        extra: Record<string, unknown> = {},
      ) {
        terminalSent = true;
        emit({
          type: "error",
          error: message,
          completion_source: completionSource,
          probe_status: probeStatus,
          repair_attempted: repairAttempted,
          terminal_cause: terminalCause || "error",
          ...runtimeFields(),
          ...extra,
        });
      }

      function conflictCode(result: unknown): string | undefined {
        if (!isRecord(result)) return undefined;
        return typeof result.code === "string" ? result.code : undefined;
      }

      async function postAiMove(
        placements: PlacementData[],
        source: CompletionSource,
      ): Promise<Record<string, unknown> | null> {
        completionSource = source;
        const moveResult = await backendPost(
          `/api/game/${game_id}/ai-move/`,
          { placements, ai_metadata: boundedAiMetadata(source) },
          token,
        );
        if (!isLegalBackendTerminal(moveResult)) return null;
        return moveResult as Record<string, unknown>;
      }

      async function commitBestAvailable(
        opts?: { terminalCause?: string },
      ): Promise<boolean> {
        const choices = await rankedAndProviderChoices();
        if (choices.length === 0) return false;
        for (const candidate of choices) {
          terminalCause = opts?.terminalCause ?? candidate.source;
          const moveResult = await postAiMove(
            candidate.placements,
            candidate.source,
          );
          if (!moveResult) continue;
          const appliedWords = Array.isArray(moveResult.words)
            ? (moveResult.words as Array<{ word?: string; score?: number }>)
            : [];
          emitDone("place", moveResult, {
            best_word: appliedWords[0]?.word ?? candidate.word,
            best_score:
              moveResult.points ?? appliedWords[0]?.score ?? candidate.score,
          });
          return true;
        }
        return false;
      }

      async function runRepair(witnessPlacements: PlacementData[]): Promise<void> {
        if (
          !runGenerationImpl ||
          !languageModel ||
          !forceValidateMoveConfig ||
          remainingSeconds() < REPAIR_MIN_REMAINING_SECONDS
        ) {
          return;
        }
        const remainingSteps = maxSteps - attemptProviderRequests();
        if (remainingSteps < REPAIR_RESERVE_STEPS) return;

        const repairModel = languageModel;
        const repairValidate = forceValidateMoveConfig;
        const repairGenerate = runGenerationImpl;
        repairAttempted = true;
        const repairAbort = new AbortController();
        const repairMs = Math.max(remainingSeconds() * 1000, 0);
        const repairTimer = setTimeout(() => repairAbort.abort(), repairMs);
        const repairPrompt =
          `${userPrompt}\n\nREPAIR WITNESS (authoritative placements; call validateMove ` +
          `exactly on these tiles):\n${JSON.stringify({ placements: witnessPlacements })}`;
        try {
          repairResult = await repairGenerate(repairModel, {
            temperature: REPAIR_TEMPERATURE,
            stepCap: REPAIR_RESERVE_STEPS,
            prompt: repairPrompt,
            abortSignal: repairAbort.signal,
            prepareStep: () => repairValidate,
          });
        } catch (err) {
          if (!(err instanceof DOMException && err.name === "AbortError")) {
            throw err;
          }
        } finally {
          clearTimeout(repairTimer);
          noteGenerationResult(repairResult);
        }
      }

      async function probeAndResolve(
        cause: string,
        opts?: { allowProviderRepair?: boolean },
      ): Promise<void> {
        const allowProviderRepair = opts?.allowProviderRepair !== false;
        terminalCause = cause;
        let playability: PlayabilityPayload;
        try {
          playability = (await backendGet(
            `/api/game/${game_id}/ai-playability/`,
            token,
          )) as PlayabilityPayload;
        } catch {
          probeStatus = "failed";
          emitTerminalError("Playability could not be determined.", {
            code: "playability_unknown",
          });
          return;
        }

        if (playability.ok === false || typeof playability.status !== "string") {
          probeStatus =
            typeof playability.code === "string" ? playability.code : "failed";
          emitTerminalError(
            typeof playability.error === "string"
              ? playability.error
              : "Playability could not be determined.",
            {
              code:
                typeof playability.code === "string"
                  ? playability.code
                  : "playability_unknown",
            },
          );
          return;
        }

        probeStatus = playability.status;

        if (playability.status === "found") {
          const witnessPlacements = normalizePlacementArray(
            isRecord(playability.witness) ? playability.witness.placements : null,
          );
          if (witnessPlacements.length === 0) {
            emitTerminalError("Playability witness was missing.", {
              code: "playability_unknown",
            });
            return;
          }

          const knownKeys = new Set(
            candidates.filter((c) => c.valid).map((c) => placementKey(c.placements)),
          );
          const remainingSteps = maxSteps - attemptProviderRequests();
          if (
            allowProviderRepair &&
            remainingSteps >= REPAIR_RESERVE_STEPS &&
            remainingSeconds() >= REPAIR_MIN_REMAINING_SECONDS
          ) {
            emit({
              type: "thinking",
              status: "probe_found",
              message: "backend found a legal rescue; repairing",
              probe_status: "found",
            });
            await runRepair(witnessPlacements);
            const repairCandidates = candidates
              .filter((c) => c.valid)
              .filter((c) => !knownKeys.has(placementKey(c.placements)))
              .sort((a, b) => b.score - a.score);
            for (const candidate of repairCandidates) {
              terminalCause = "repair_candidate";
              const moveResult = await postAiMove(
                candidate.placements,
                "repair_candidate",
              );
              if (!moveResult) continue;
              const appliedWords = Array.isArray(moveResult.words)
                ? (moveResult.words as Array<{ word?: string; score?: number }>)
                : [];
              emitDone("place", moveResult, {
                best_word: appliedWords[0]?.word ?? candidate.word,
                best_score:
                  moveResult.points ?? appliedWords[0]?.score ?? candidate.score,
              });
              return;
            }
          }

          terminalCause = "backend_witness_rescue";
          const rescue = await postAiMove(
            witnessPlacements,
            "backend_witness_rescue",
          );
          if (!rescue) {
            emitTerminalError("The AI action was not accepted.", {
              code: "stale_witness",
            });
            return;
          }
          const appliedWords = Array.isArray(rescue.words)
            ? (rescue.words as Array<{ word?: string; score?: number }>)
            : [];
          emitDone("place", rescue, {
            best_word: appliedWords[0]?.word,
            best_score: rescue.points ?? appliedWords[0]?.score,
          });
          return;
        }

        if (playability.status === "none") {
          if (playability.exchange_allowed === true) {
            const letters = Array.isArray(playability.exchange_letters)
              ? playability.exchange_letters.filter(
                  (letter: unknown): letter is string =>
                    typeof letter === "string" && letter.length === 1,
                )
              : [];
            terminalCause = "genuine_no_move_exchange";
            completionSource = "genuine_no_move_exchange";
            emit({
              type: "thinking",
              status: "genuine_exchange",
              message: "genuine dead rack — exchanging",
              probe_status: "none",
            });
            const exchangeResult = await backendPost(
              `/api/game/${game_id}/ai-exchange/`,
              {
                letters,
                ai_metadata: boundedAiMetadata("genuine_no_move_exchange"),
              },
              token,
            );
            if (!isLegalBackendTerminal(exchangeResult)) {
              emitTerminalError("The AI action was not accepted.", {
                code: conflictCode(exchangeResult),
              });
              return;
            }
            emitDone("exchange", exchangeResult as Record<string, unknown>);
            return;
          }

          terminalCause = "genuine_no_move_pass";
          completionSource = "genuine_no_move_pass";
          emit({
            type: "thinking",
            status: "genuine_pass",
            message: "genuine dead rack — passing",
            probe_status: "none",
          });
          const passResult = await backendPost(
            `/api/game/${game_id}/ai-pass/`,
            { ai_metadata: boundedAiMetadata("genuine_no_move_pass") },
            token,
          );
          if (!isLegalBackendTerminal(passResult)) {
            emitTerminalError("The AI action was not accepted.", {
              code: conflictCode(passResult),
            });
            return;
          }
          emitDone("pass", passResult as Record<string, unknown>);
          return;
        }

        emitTerminalError("Playability could not be determined.", {
          code: "playability_unknown",
        });
      }

      try {
        const catalogRows = await fetchCatalogModelRows();
        if (catalogRows === null) {
          emit({
            type: "error",
            code: "provider_unavailable",
            error:
              "This free rival is temporarily unavailable. Switch to another free rival or retry later.",
            provider_path: providerPath,
            runtime_model: runtimeModelId,
          });
          closeStream();
          return;
        }

        const context = await backendGet(
          `/api/game/${game_id}/ai-context/`,
          token,
        );
        promptContext = context;

        if (!context.compact_state) {
          emit({ type: "error", error: "Could not fetch game context" });
          closeStream();
          return;
        }

        sessionModelId =
          typeof context.ai_model_id === "string" ? context.ai_model_id : null;

        const resolvedPair =
          findCatalogPair(requestedModelId, catalogRows) ??
          findCatalogPair(sessionModelId, catalogRows) ??
          findCatalogPair(catalogRows[0]?.model_id, catalogRows);
        if (!resolvedPair) {
          emit({
            type: "error",
            code: "provider_unavailable",
            error:
              "This free rival is temporarily unavailable. Switch to another free rival or retry later.",
            provider_path: providerPath,
            runtime_model: runtimeModelId,
          });
          closeStream();
          return;
        }
        const resolvedModelId = resolvedPair.model_id;

        if (
          requestedModelId &&
          requestedModelId === resolvedPair.model_id &&
          requestedModelId !== sessionModelId
        ) {
          const updateResult = await backendPatch(
            `/api/game/${game_id}/ai-model/`,
            { ai_model_model_id: requestedModelId },
            token,
          );
          if (updateResult.ok === false) {
            emit({
              type: "error",
              error: updateResult.error ?? "Could not switch AI model",
              provider_path: providerPath,
              runtime_model: runtimeModelId,
            });
            closeStream();
            return;
          }
        }
        const backendMaxOutputTokens =
          typeof context.ai_move_max_output_tokens === "number"
            ? context.ai_move_max_output_tokens
            : Number.parseInt(String(context.ai_move_max_output_tokens ?? ""), 10);
        const requestedMaxOutputTokens = Number.isFinite(backendMaxOutputTokens)
          ? clampNumber(
              backendMaxOutputTokens,
              MIN_MAX_OUTPUT_TOKENS,
              MAX_MAX_OUTPUT_TOKENS,
            )
          : DEFAULT_MAX_OUTPUT_TOKENS;
        const requestedRuntimePair =
          requestedRuntimeModelId
            ? findCatalogPair(requestedRuntimeModelId, catalogRows)
            : null;
        const runtimePair =
          requestedRuntimePair &&
          revalidateRuntimePair(
            requestedRuntimePair.provider,
            requestedRuntimePair.model_id,
            catalogRows,
          )
            ? requestedRuntimePair
            : resolvedPair;
        if (!revalidateRuntimePair(runtimePair.provider, runtimePair.model_id, catalogRows)) {
          emit({
            type: "error",
            code: "provider_unavailable",
            error:
              "This free rival is temporarily unavailable. Switch to another free rival or retry later.",
            provider_path: providerPath,
            runtime_model: runtimeModelId,
          });
          closeStream();
          return;
        }
        runtimeModelId = runtimePair.model_id;
        providerPath = runtimePair.provider;
        const maxOutputTokens = requestedMaxOutputTokens;
        const useExtendedSearchBudget = timeoutS >= 90 || maxSteps >= 45;
        autoFinalizeGraceMs = useExtendedSearchBudget
          ? EXTENDED_AUTO_FINALIZE_GRACE_MS
          : AUTO_FINALIZE_GRACE_MS;
        autoFinalizeValidCap = useExtendedSearchBudget
          ? EXTENDED_AUTO_FINALIZE_VALID_CAP
          : AUTO_FINALIZE_VALID_CAP;

        const moveSpec = movePromptSpecFromContext(context);
        const systemPrompt = composeMoveSystemPrompt(
          typeof context.ai_prompt_text === "string" ? context.ai_prompt_text : null,
          moveSpec,
        );
        userPrompt = buildMoveUserPrompt(context);
        let model: Awaited<ReturnType<typeof getLanguageRuntime>>["model"];
        try {
          const runtime = await getLanguageRuntime(
            runtimePair.provider,
            runtimePair.model_id,
          );
          model = runtime.model;
          languageModel = model;
          runtimeTracker = runtime.tracker;
        } catch (err) {
          const normalizedError = normalizeProviderError(err) ?? {
            code: "provider_auth_failed" as const,
            message:
              "This free rival could not authenticate. Switch to another free rival or retry later.",
          };
          emit({
            type: "error",
            code: normalizedError.code,
            error: normalizedError.message,
            provider_path: providerPath,
            runtime_model: runtimeModelId,
            ...retryAfterFields(),
          });
          closeStream();
          return;
        }

        emit({
          type: "thinking",
          model: resolvedModelId,
          runtime_model: runtimeModelId,
          timeout: timeoutS,
          max_steps: maxSteps,
          max_output_tokens: maxOutputTokens,
          requested_max_output_tokens: requestedMaxOutputTokens,
          provider_path: providerPath,
        });
        emit({
          type: "thinking",
          status: "searching",
          message: "Exploring legal words and validating the board...",
          provider_path: providerPath,
          runtime_model: runtimeModelId,
        });

        const tools = {
          validateMove: tool({
            description:
              "Validate a proposed tile placement on the board. Returns " +
              "legality, all words formed, per-word scores, and total score. " +
              "Call this FIRST with your best candidate. Only use it for " +
              "plausible English candidates, hooks, extensions, or premium shots, " +
              "not random dictionary guesses.",
            inputSchema: z.object({
              placements: z
                .array(placementSchema)
                .min(1)
                .max(7)
                .describe("Tiles to place on the board"),
            }),
            execute: async ({ placements }) => {
              emit({
                type: "tool_use",
                tool: "validateMove",
                tileCount: placements.length,
              });

              const result = await backendPost(
                `/api/game/${game_id}/validate-move/`,
                { placements, rack_owner: "ai" },
                token,
              );

              emit({
                type: "tool_result",
                tool: "validateMove",
                valid: result.valid,
                score: result.total_score,
                words: result.words,
              });

              trackCandidate(result, placements);
              return result;
            },
          }),

          finishMove: tool({
            description:
              "Signal that a backend-validated placement is ready to finalize. " +
              "Call only after validateMove has returned a valid result. " +
              "This tool has no other side effects.",
            inputSchema: z.object({
              ready: z.literal(true).describe("Must be true to finalize"),
            }),
            execute: async () => {
              emit({
                type: "tool_use",
                tool: "finishMove",
              });
              queueMicrotask(() => abortGeneration("finish"));
              return { ok: true };
            },
          }),
        };

        const forceValidateMove = {
          activeTools: ["validateMove"] as Array<keyof typeof tools>,
          toolChoice: { type: "tool" as const, toolName: "validateMove" as const },
        };
        forceValidateMoveConfig = forceValidateMove;

        function prepareSearchStep({ stepNumber }: { stepNumber: number }) {
          if (stepNumber === 0 || getBestCandidate() === null) {
            return forceValidateMove;
          }
          return {
            activeTools: ["validateMove", "finishMove"] as Array<keyof typeof tools>,
          };
        }

        const runGeneration = (
          activeModel: Awaited<ReturnType<typeof getLanguageRuntime>>["model"],
          args: {
            temperature: number;
            stepCap: number;
            prompt: string;
            abortSignal: AbortSignal;
            prepareStep: (options: { stepNumber: number }) => {
              activeTools: Array<keyof typeof tools>;
              toolChoice?: { type: "tool"; toolName: "validateMove" };
            };
          },
        ) =>
          Promise.race([
            generateText({
              model: activeModel,
              maxOutputTokens,
              temperature: args.temperature,
              maxRetries: 0,
              system: systemPrompt,
              prompt: args.prompt,
              abortSignal: args.abortSignal,
              tools,
              prepareStep: args.prepareStep,
              stopWhen: stepCountIs(args.stepCap),
              onStepFinish: (step) => {
                completedStepCount += 1;
                runtimeTracker?.recordUsage(step.usage);
                accumulatedUsage = mergeUsage(
                  accumulatedUsage,
                  normalizeUsage(step.usage as UsageLike | undefined),
                );
                lastResponseModelId = step.response.modelId;
              },
            }),
            new Promise<never>((_, reject) => {
              args.abortSignal.addEventListener(
                "abort",
                () => {
                  reject(new DOMException("Timeout", "AbortError"));
                },
                { once: true },
              );
            }),
          ]);

        runGenerationImpl = runGeneration;

        const timeoutId = setTimeout(() => {
          abortGeneration("timeout");
        }, timeoutS * 1000);

        try {
          try {
            aiResult = await runGeneration(model, {
              temperature: SEARCH_TEMPERATURE,
              stepCap: searchStepCap,
              prompt: userPrompt,
              abortSignal: abortController.signal,
              prepareStep: prepareSearchStep,
            });
          } catch (err) {
            if (err instanceof DOMException && err.name === "AbortError") {
              // timeout / auto-finalize / finishMove — continue with tracked candidates
            } else {
              throw err;
            }
          } finally {
            clearAutoFinalizeTimer();
            noteGenerationResult(aiResult);
          }

          const timedOut = abortReason === "timeout";
          const best = getBestCandidate();
          if (best) {
            if (timedOut) {
              emit({
                type: "candidate",
                word: best.word,
                score: best.score,
                valid: true,
                isBest: true,
                allWords: best.allWords,
                isTimeout: true,
                auto_finalized: autoFinalized,
                timestamp: Date.now() - startTime,
              });
            }
          }
          const committed = await commitBestAvailable();
          if (committed) {
            closeStream();
            return;
          }
          await probeAndResolve(
            best
              ? "commit_rejected"
              : timedOut
                ? "timeout_no_candidate"
                : "no_valid_candidate",
          );
        } finally {
          clearTimeout(timeoutId);
          clearAutoFinalizeTimer();
        }
      } catch (error) {
        const normalizedError = normalizeProviderError(error);
        if (normalizedError) {
          emit({
            type: "error",
            code: normalizedError.code,
            error: normalizedError.message,
            provider_path: providerPath,
            runtime_model: runtimeModelId,
            provider_requests_used: attemptProviderRequests(),
            turn_provider_requests_used: attemptProviderRequests(),
            ...retryAfterFields(),
            repair_attempted: repairAttempted,
            probe_status: probeStatus,
            terminal_cause: "provider_error",
          });
          closeStream();
          return;
        }

        // A generic SDK/runtime exception may still use ranked candidates
        // even with no tracked provider move. Classified provider/endpoint
        // failures above must remain eligible for the outer three-lane
        // fallback instead of becoming backend-only.
        try {
          const committed = await commitBestAvailable({
            terminalCause: "generic_error_fallback",
          });
          if (committed) {
            return;
          }
          if (!terminalSent) {
            await probeAndResolve("generic_runtime", {
              allowProviderRepair: false,
            });
          }
          if (!terminalSent) {
            terminalCause = "backend_rescue_error";
            emitTerminalError(BOUNDED_INTERNAL_ERROR, {
              code: "ai_move_internal_error",
            });
          }
        } catch {
          if (!terminalSent) {
            terminalCause = "backend_rescue_error";
            emitTerminalError(BOUNDED_INTERNAL_ERROR, {
              code: "ai_move_internal_error",
            });
          }
        }
      } finally {
        closeStream();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
