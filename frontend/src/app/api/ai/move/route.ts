/**
 * AI Move Generation API Route — SSE Streaming
 *
 * Streams real-time progress events to the frontend while the AI agent
 * searches for the best Scrabble move. This mirrors the desktop scrabgpt
 * agent's tool-calling workflow with live feedback.
 *
 * SSE Event Flow:
 *   thinking    → AI started, timeout set
 *   tool_use    → AI called validateMove / validateWords
 *   tool_result → Tool returned a result
 *   candidate   → Valid move candidate found (word, score, isBest)
 *   done        → Final move applied (or pass/exchange fallback)
 *   error       → Something went wrong
 *
 * Timeout:
 *   When the timeout expires, the best candidate found so far is used.
 *   If no valid candidate exists, AI exchanges or passes.
 */

import { NextRequest } from "next/server";
import { generateText, tool, stepCountIs } from "ai";
import { z } from "zod";
import {
  canUseDirectOpenAIModel,
  getDirectModel,
  getModel,
  getProviderPath,
  isGatewayConfigured,
} from "@/lib/ai-gateway";
import { isLocalAIModelId } from "@/lib/local-ai";
import { resolveLMStudioRuntimeModelId } from "@/lib/lm-studio";
import {
  LOCAL_MOVE_SYSTEM_PROMPT,
  MOVE_SYSTEM_PROMPT,
  buildLocalMoveUserPrompt,
  buildMoveUserPrompt,
} from "@/lib/prompts";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const DEFAULT_TIMEOUT_S = 30;
const DEFAULT_MAX_STEPS = 30;
const MIN_STEPS = 5;
const MAX_STEPS = 100;
const DEFAULT_MAX_OUTPUT_TOKENS = 10000;
const MIN_MAX_OUTPUT_TOKENS = 2000;
const MAX_MAX_OUTPUT_TOKENS = 64000;
const DEFAULT_LM_STUDIO_MAX_OUTPUT_TOKENS = 4096;
const MIN_LM_STUDIO_MAX_OUTPUT_TOKENS = 512;
const MAX_LM_STUDIO_MAX_OUTPUT_TOKENS = 8192;
const AUTO_FINALIZE_GRACE_MS = 2500;
const AUTO_FINALIZE_VALID_CAP = 4;
const EXTENDED_AUTO_FINALIZE_GRACE_MS = 6000;
const EXTENDED_AUTO_FINALIZE_VALID_CAP = 7;
const LOCAL_OPENING_FALLBACK_WORDS = [
  "FILMS",
  "MAILS",
  "SLIM",
  "FAIL",
  "FILM",
  "FILS",
  "ABLE",
  "BAIL",
  "BAILS",
  "AILS",
  "AIMS",
  "ALBS",
  "ALMS",
  "AMIS",
  "BIAS",
  "BALM",
  "BALMS",
  "BAMS",
  "LAMS",
  "LIBS",
  "MILS",
  "SIMA",
  "AIS",
  "ALS",
  "AMI",
  "BAM",
  "BAS",
  "BIS",
  "FAS",
  "IFS",
  "ISM",
  "LAM",
  "LIB",
  "LIS",
  "MIL",
  "MIS",
  "SIB",
  "SIM",
  "AA",
  "AB",
  "AD",
  "AE",
  "AG",
  "AH",
  "AI",
  "AL",
  "AM",
  "AN",
  "AR",
  "AS",
  "AW",
  "AX",
  "AY",
  "BA",
  "BE",
  "BI",
  "BO",
  "BY",
  "DA",
  "DE",
  "DO",
  "ED",
  "EF",
  "EH",
  "EL",
  "EM",
  "EN",
  "ER",
  "ES",
  "ET",
  "EW",
  "EX",
  "FA",
  "FE",
  "FY",
  "GI",
  "GO",
  "GU",
  "HA",
  "HE",
  "HI",
  "HM",
  "HO",
  "ID",
  "IF",
  "IN",
  "IO",
  "IS",
  "IT",
  "JO",
  "KA",
  "KI",
  "KO",
  "KY",
  "LA",
  "LI",
  "LO",
  "MA",
  "ME",
  "MI",
  "MM",
  "MO",
  "MU",
  "MY",
  "NA",
  "NE",
  "NO",
  "NU",
  "OD",
  "OE",
  "OF",
  "OH",
  "OI",
  "OM",
  "ON",
  "OO",
  "OP",
  "OR",
  "OS",
  "OU",
  "OW",
  "OX",
  "OY",
  "PA",
  "PE",
  "PI",
  "PO",
  "QI",
  "RE",
  "SH",
  "SI",
  "SO",
  "ST",
  "TA",
  "TE",
  "TI",
  "TO",
  "UG",
  "UH",
  "UM",
  "UN",
  "UP",
  "UR",
  "US",
  "UT",
  "WE",
  "WO",
  "XI",
  "XU",
  "YA",
  "YE",
  "YO",
  "ZA",
];

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

async function chargeAITurn(
  gameId: string,
  token: string,
  aiMetadata: Record<string, unknown>,
) {
  return backendPost(
    "/api/billing/charge-ai-turn/",
    { game_id: gameId, ai_metadata: aiMetadata },
    token,
  );
}

const placementSchema = z.object({
  row: z.number().min(0).max(14).describe("Row index (0-14)"),
  col: z.number().min(0).max(14).describe("Column index (0-14)"),
  letter: z.string().length(1).describe("Tile letter (A-Z) or ? for blank"),
  blank_as: z
    .string()
    .length(1)
    .optional()
    .describe("If letter is ?, the letter it represents"),
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

type NormalizedRouteError = {
  code: "insufficient_user_credit" | "insufficient_provider_funds";
  message: string;
};

function sseEvent(data: Record<string, unknown>): string {
  return `data: ${JSON.stringify(data)}\n\n`;
}

function normalizeRouteError(error: unknown): NormalizedRouteError | null {
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();

  if (
    normalized.includes("insufficient funds") ||
    normalized.includes("add credits to your account") ||
    normalized.includes("top up your credits")
  ) {
    return {
      code: "insufficient_provider_funds",
      message:
        "The shared AI provider budget is temporarily exhausted. Your personal balance is untouched. Switch models or try again later.",
    };
  }

  return null;
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
  const letter = typeof value.letter === "string" ? value.letter.trim().toUpperCase() : null;
  const blankAs =
    typeof value.blank_as === "string"
      ? value.blank_as.trim().toUpperCase()
      : typeof value.blankAs === "string"
        ? value.blankAs.trim().toUpperCase()
        : null;

  if (row === null || col === null || !letter || letter.length !== 1) {
    return null;
  }

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

function extractLocalPlacementArray(parsed: unknown): PlacementData[] {
  if (!isRecord(parsed)) return [];

  const directPlacements = normalizePlacementArray(parsed.placements);
  if (directPlacements.length > 0) return directPlacements;

  const tilePlacements = normalizePlacementArray(parsed.tiles);
  if (tilePlacements.length > 0) return tilePlacements;

  if (isRecord(parsed.move)) {
    const movePlacements = normalizePlacementArray(parsed.move.placements);
    if (movePlacements.length > 0) return movePlacements;
  }

  for (const value of Object.values(parsed)) {
    const placements = normalizePlacementArray(value);
    if (placements.length > 0) return placements;
  }

  return [];
}

function extractJsonObject(text: string, requireAction: boolean): unknown | null {
  for (let start = text.indexOf("{"); start >= 0; start = text.indexOf("{", start + 1)) {
    let depth = 0;
    let inString = false;
    let escaped = false;

    for (let index = start; index < text.length; index += 1) {
      const char = text[index];

      if (inString) {
        if (escaped) {
          escaped = false;
        } else if (char === "\\") {
          escaped = true;
        } else if (char === "\"") {
          inString = false;
        }
        continue;
      }

      if (char === "\"") {
        inString = true;
      } else if (char === "{") {
        depth += 1;
      } else if (char === "}") {
        depth -= 1;
        if (depth === 0) {
          const candidate = text.slice(start, index + 1);
          if (requireAction && !candidate.includes("\"action\"")) break;
          try {
            return JSON.parse(candidate);
          } catch {
            break;
          }
        }
      }
    }
  }

  return null;
}

function getLMStudioMaxOutputTokens() {
  const configured = Number.parseInt(
    process.env.LM_STUDIO_MAX_OUTPUT_TOKENS ?? "",
    10,
  );

  if (!Number.isFinite(configured)) {
    return DEFAULT_LM_STUDIO_MAX_OUTPUT_TOKENS;
  }

  return clampNumber(
    configured,
    MIN_LM_STUDIO_MAX_OUTPUT_TOKENS,
    MAX_LM_STUDIO_MAX_OUTPUT_TOKENS,
  );
}

function canBuildWordFromRack(word: string, rack: string): boolean {
  const counts = new Map<string, number>();
  for (const letter of rack.toUpperCase()) {
    counts.set(letter, (counts.get(letter) ?? 0) + 1);
  }

  for (const letter of word.toUpperCase()) {
    const available = counts.get(letter) ?? 0;
    const blanks = counts.get("?") ?? 0;
    if (available > 0) {
      counts.set(letter, available - 1);
    } else if (blanks > 0) {
      counts.set("?", blanks - 1);
    } else {
      return false;
    }
  }

  return true;
}

function buildOpeningPlacements(word: string): PlacementData[] {
  const startCol = 7 - Math.floor(word.length / 2);
  return word.split("").map((letter, index) => ({
    row: 7,
    col: startCol + index,
    letter,
  }));
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { game_id, token, model_id, timeout } = body as {
    game_id: string;
    token: string;
    model_id?: string;
    timeout?: number;
    max_steps?: number;
  };

  const timeoutS = Math.max(15, Math.min(timeout ?? DEFAULT_TIMEOUT_S, 600));
  const maxSteps = Math.max(
    MIN_STEPS,
    Math.min(
      typeof body.max_steps === "number" ? body.max_steps : DEFAULT_MAX_STEPS,
      MAX_STEPS,
    ),
  );
  const startTime = Date.now();
  const requestedModelId = model_id || null;

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

      // Track candidates across all tool calls
      const candidates: Candidate[] = [];
      let bestScore = -1;
      let autoFinalized = false;
      let autoFinalizeTimer: ReturnType<typeof setTimeout> | null = null;
      const abortController = new AbortController();
      let autoFinalizeGraceMs = AUTO_FINALIZE_GRACE_MS;
      let autoFinalizeValidCap = AUTO_FINALIZE_VALID_CAP;
      let accumulatedUsage: ReturnType<typeof normalizeUsage> = null;
      let completedStepCount = 0;
      let completedToolCallCount = 0;
      const completedStepModels: Array<{
        step: number;
        provider: string;
        model_id: string;
        response_model: string | undefined;
      }> = [];
      let lastResponseModelId: string | undefined;

      function clearAutoFinalizeTimer() {
        if (autoFinalizeTimer) {
          clearTimeout(autoFinalizeTimer);
          autoFinalizeTimer = null;
        }
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
            });

            if (validCount >= autoFinalizeValidCap) {
              autoFinalized = true;
              abortController.abort();
            } else {
              autoFinalizeTimer = setTimeout(() => {
                autoFinalized = true;
                abortController.abort();
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

      try {
        if (requestedModelId) {
          const updateResult = await backendPatch(
            `/api/game/${game_id}/ai-model/`,
            { ai_model_model_id: requestedModelId },
            token,
          );
          if (updateResult.ok === false) {
            emit({
              type: "error",
              error: updateResult.error ?? "Could not switch AI model",
            });
            closeStream();
            return;
          }
        }

        // 1. Fetch game context
        const context = await backendGet(
          `/api/game/${game_id}/ai-context/`,
          token,
        );

        if (!context.compact_state) {
          emit({ type: "error", error: "Could not fetch game context" });
          closeStream();
          return;
        }

        const sessionModelId =
          typeof context.ai_model_id === "string" ? context.ai_model_id : null;
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
        const resolvedModelId =
          requestedModelId ||
          sessionModelId ||
          process.env.NEXT_PUBLIC_DEFAULT_MODEL ||
          "openai/gpt-5.4";
        const isLocalModel = isLocalAIModelId(resolvedModelId);
        const localMaxOutputTokens = isLocalModel ? getLMStudioMaxOutputTokens() : null;
        const maxOutputTokens =
          localMaxOutputTokens !== null
            ? Math.min(requestedMaxOutputTokens, localMaxOutputTokens)
            : requestedMaxOutputTokens;
        const useExtendedSearchBudget = timeoutS >= 90 || maxSteps >= 45;
        autoFinalizeGraceMs = useExtendedSearchBudget
          ? EXTENDED_AUTO_FINALIZE_GRACE_MS
          : AUTO_FINALIZE_GRACE_MS;
        autoFinalizeValidCap = useExtendedSearchBudget
          ? EXTENDED_AUTO_FINALIZE_VALID_CAP
          : AUTO_FINALIZE_VALID_CAP;
        const profile = await backendGet("/api/auth/me/", token).catch(() => null);
        const availableCredits =
          typeof profile?.credit_balance === "string"
            ? Number.parseFloat(profile.credit_balance)
            : Number.NaN;

        if (!isLocalModel && Number.isFinite(availableCredits) && availableCredits <= 0) {
          emit({
            type: "error",
            code: "insufficient_user_credit",
            error:
              "Your balance is empty. Open settings to top up or switch to a cheaper AI model.",
            credit_balance: profile.credit_balance,
          });
          closeStream();
          return;
        }

        const activeMovePrompt =
          typeof context.ai_prompt_text === "string" && context.ai_prompt_text.trim().length > 0
            ? context.ai_prompt_text
            : MOVE_SYSTEM_PROMPT;
        const runtimeModelId = isLocalModel
          ? await resolveLMStudioRuntimeModelId(resolvedModelId)
          : resolvedModelId;
        if (!runtimeModelId) {
          emit({
            type: "error",
            error:
              "LM Studio is reachable, but no loaded tool-capable chat model is available. Load a model in LM Studio and try again.",
          });
          closeStream();
          return;
        }

        const model = getModel(
          isLocalModel && runtimeModelId !== resolvedModelId
            ? `lmstudio/${runtimeModelId}`
            : resolvedModelId,
        );
        let providerPath = getProviderPath(resolvedModelId);
        let gatewayFallbackUsed = false;

        if (isLocalModel && runtimeModelId !== resolvedModelId) {
          emit({
            type: "thinking",
            status: "local_model_resolved",
            message: `Using loaded LM Studio model ${runtimeModelId}.`,
          });
        }

        emit({
          type: "thinking",
          model: resolvedModelId,
          runtime_model: runtimeModelId,
          timeout: timeoutS,
          max_steps: maxSteps,
          max_output_tokens: maxOutputTokens,
          requested_max_output_tokens: requestedMaxOutputTokens,
          local_max_output_tokens: localMaxOutputTokens,
          provider_path: providerPath,
        });
        emit({
          type: "thinking",
          status: "searching",
          message: isLocalModel
            ? "Using compact local prompt and server-side final validation..."
            : "Exploring legal words and validating the board...",
        });

        const runLocalGeneration = (activeModel: ReturnType<typeof getModel>) =>
          Promise.race([
            generateText({
              model: activeModel,
              maxOutputTokens,
              temperature: 0.1,
              system: LOCAL_MOVE_SYSTEM_PROMPT,
              prompt: buildLocalMoveUserPrompt(context),
              providerOptions: {
                openai: {
                  reasoningEffort: "none",
                },
              },
              abortSignal: abortController.signal,
              stopWhen: stepCountIs(1),
              onStepFinish: (step) => {
                completedStepCount += 1;
                completedToolCallCount += step.toolCalls.length;
                accumulatedUsage = mergeUsage(
                  accumulatedUsage,
                  normalizeUsage(step.usage as UsageLike | undefined),
                );
                completedStepModels.push({
                  step: step.stepNumber,
                  provider: step.model.provider,
                  model_id: step.model.modelId,
                  response_model: step.response.modelId,
                });
                lastResponseModelId = step.response.modelId;
              },
            }),
            new Promise<never>((_, reject) => {
              abortController.signal.addEventListener("abort", () => {
                reject(new DOMException("Timeout", "AbortError"));
              });
            }),
          ]);

        const runGeneration = (activeModel: ReturnType<typeof getModel>) =>
          Promise.race([
            generateText({
              model: activeModel,
              maxOutputTokens,
              temperature: 0.15,
              system: activeMovePrompt,
              prompt: buildMoveUserPrompt(context),
              abortSignal: abortController.signal,
              tools: {
                validateMove: tool({
                  description:
                    "Validate a proposed tile placement on the board. Returns " +
                    "legality, all words formed, per-word scores, and total score. " +
                    "Call this BEFORE finalizing any move. Only use it for " +
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
                      { placements },
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

                validateWords: tool({
                  description:
                    "Check if words are valid in the Collins Scrabble Words " +
                    "(2019) English dictionary (279,496 words). Use this only " +
                    "to confirm words formed by a plausible legal placement, never to brainstorm random strings.",
                  inputSchema: z.object({
                    words: z
                      .array(z.string())
                      .min(1)
                      .describe("Words to check"),
                  }),
                  execute: async ({ words }) => {
                    emit({
                      type: "tool_use",
                      tool: "validateWords",
                      words,
                    });

                    const result = await backendPost(
                      `/api/game/${game_id}/validate-words/`,
                      { words },
                      token,
                    );

                    emit({
                      type: "tool_result",
                      tool: "validateWords",
                      results: result.results,
                    });

                    return result;
                  },
                }),
              },
              stopWhen: stepCountIs(maxSteps),
              onStepFinish: (step) => {
                completedStepCount += 1;
                completedToolCallCount += step.toolCalls.length;
                accumulatedUsage = mergeUsage(
                  accumulatedUsage,
                  normalizeUsage(step.usage as UsageLike | undefined),
                );
                completedStepModels.push({
                  step: step.stepNumber,
                  provider: step.model.provider,
                  model_id: step.model.modelId,
                  response_model: step.response.modelId,
                });
                lastResponseModelId = step.response.modelId;
              },
            }),
            new Promise<never>((_, reject) => {
              abortController.signal.addEventListener("abort", () => {
                reject(new DOMException("Timeout", "AbortError"));
              });
            }),
          ]);

        // 2. Race: generateText vs timeout
        const timeoutId = setTimeout(() => {
          abortController.abort();
        }, timeoutS * 1000);

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let aiResult: any = null;
        let timedOut = false;

        try {
          aiResult = await (isLocalModel
            ? runLocalGeneration(model)
            : runGeneration(model));
        } catch (err) {
          if (err instanceof DOMException && err.name === "AbortError") {
            timedOut = true;
          } else {
            const normalizedError = normalizeRouteError(err);
            const shouldFallbackToDirectOpenAI =
              normalizedError?.code === "insufficient_provider_funds" &&
              isGatewayConfigured() &&
              canUseDirectOpenAIModel(resolvedModelId);

            if (!shouldFallbackToDirectOpenAI) {
              throw err;
            }

            emit({
              type: "thinking",
              status: "provider_fallback",
              message:
                "The shared AI Gateway budget is exhausted. Retrying directly with OpenAI for this model...",
            });

            try {
              aiResult = await runGeneration(getDirectModel(resolvedModelId));
              providerPath = "direct_openai";
              gatewayFallbackUsed = true;
            } catch (fallbackError) {
              if (
                fallbackError instanceof DOMException &&
                fallbackError.name === "AbortError"
              ) {
                timedOut = true;
              } else {
                throw fallbackError;
              }
            }
          }
        } finally {
          clearTimeout(timeoutId);
          clearAutoFinalizeTimer();
        }

        // 3. Determine final move
        const elapsedMs = Date.now() - startTime;
        let finalPlacements: PlacementData[] = [];
        let finalAction = "place";
        let exchangeLetters: string[] = [];

        if (timedOut) {
          // Use best tracked candidate
          const best = getBestCandidate();
          if (best) {
            finalPlacements = best.placements;
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
          } else {
            finalAction = "pass";
          }
        } else if (aiResult) {
          // Parse AI response text
          const parsed =
            extractJsonObject(aiResult.text, true) ??
            (isLocalModel ? extractJsonObject(aiResult.text, false) : null);
          if (isRecord(parsed)) {
            if (typeof parsed.action === "string") {
              finalAction = parsed.action;
            }

            const parsedPlacements = extractLocalPlacementArray(parsed);
            if (parsedPlacements.length > 0) {
              finalPlacements = parsedPlacements;
            }

            if (
              finalAction === "exchange" &&
              Array.isArray(parsed.exchange_letters)
            ) {
              exchangeLetters = parsed.exchange_letters.filter(
                (letter: unknown): letter is string =>
                  typeof letter === "string" && letter.length === 1,
              );
            }
          }

          // Fallback: last validateMove tool call
          if (finalPlacements.length === 0 && aiResult.steps) {
            for (let i = aiResult.steps.length - 1; i >= 0; i--) {
              const step = aiResult.steps[i];
              for (const tc of step.toolCalls) {
                if (tc.toolName === "validateMove" && "input" in tc) {
                  const input = tc.input as {
                    placements?: PlacementData[];
                  };
                  if (input.placements && input.placements.length > 0) {
                    finalPlacements = input.placements;
                    break;
                  }
                }
              }
              if (finalPlacements.length > 0) break;
            }
          }

          if (
            isLocalModel &&
            finalPlacements.length === 0 &&
            context.is_first_move
          ) {
            const rack = String(context.ai_state?.ai_rack ?? "");
            for (const word of LOCAL_OPENING_FALLBACK_WORDS) {
              if (!canBuildWordFromRack(word, rack)) continue;
              const placements = buildOpeningPlacements(word);
              const result = await backendPost(
                `/api/game/${game_id}/validate-move/`,
                { placements },
                token,
              );
              trackCandidate(result, placements);
              if (result.valid === true) {
                finalAction = "place";
                finalPlacements = placements;
                emit({
                  type: "thinking",
                  status: "local_opening_fallback",
                  message: `Local fallback found ${word}.`,
                });
                break;
              }
            }
          }

          // If AI returned placements but we also have a better tracked candidate, prefer tracked
          const best = getBestCandidate();
          if (best && best.score > 0) {
            const currentScore = candidates.find(
              (c) =>
                c.valid &&
                JSON.stringify(c.placements) ===
                  JSON.stringify(finalPlacements),
            )?.score;

            if (!currentScore || best.score > currentScore) {
              finalPlacements = best.placements;
            }
          }
        }

        const normalizedUsage = normalizeUsage(
          (aiResult?.totalUsage as UsageLike | undefined) ??
            (aiResult?.usage as UsageLike | undefined) ??
            null,
        ) ?? accumulatedUsage;

        const aiMeta = {
          requested_model: requestedModelId,
          session_model: sessionModelId,
          model: resolvedModelId,
          runtime_model: runtimeModelId,
          provider_path: providerPath,
          gateway_fallback_used: gatewayFallbackUsed,
          max_output_tokens: maxOutputTokens,
          requested_max_output_tokens: requestedMaxOutputTokens,
          local_max_output_tokens: localMaxOutputTokens,
          response_model: aiResult?.response?.modelId ?? lastResponseModelId,
          response_id: aiResult?.response?.id,
          response_headers: aiResult?.response?.headers,
          provider_metadata: aiResult?.providerMetadata,
          usage: normalizedUsage,
          steps: aiResult?.steps?.length ?? completedStepCount,
          max_steps: maxSteps,
          auto_finalize_grace_ms: autoFinalizeGraceMs,
          auto_finalize_valid_cap: autoFinalizeValidCap,
          elapsed_ms: elapsedMs,
          candidates_found: candidates.length,
          best_score: bestScore,
          timed_out: timedOut,
          auto_finalized: autoFinalized,
          step_models:
            aiResult?.steps?.map(
              (step: {
                stepNumber: number;
                model: { provider: string; modelId: string };
                response: { modelId: string };
              }) => ({
                step: step.stepNumber,
                provider: step.model.provider,
                model_id: step.model.modelId,
                response_model: step.response.modelId,
              }),
            ) ?? completedStepModels,
          tool_calls_count:
            aiResult?.steps?.reduce(
              (sum: number, s: { toolCalls: unknown[] }) =>
                sum + s.toolCalls.length,
              0,
            ) ?? completedToolCallCount,
        };

        // 4. Apply the final move
        if (finalAction === "exchange" && exchangeLetters.length > 0) {
          const exchangeResult = await backendPost(
            `/api/game/${game_id}/ai-exchange/`,
            { letters: exchangeLetters },
            token,
          );
          const billing = await chargeAITurn(game_id, token, aiMeta);
          emit({
            type: "done",
            action: "exchange",
            ...exchangeResult,
            billing,
            requested_model: requestedModelId,
            session_model: sessionModelId,
            response_model: aiResult?.response?.modelId,
            elapsed_ms: elapsedMs,
            candidates_found: candidates.length,
            timed_out: timedOut,
            auto_finalized: autoFinalized,
          });
          closeStream();
          return;
        }

        if (finalPlacements.length === 0 || finalAction === "pass") {
          const passResult = await backendPost(
            `/api/game/${game_id}/ai-pass/`,
            {},
            token,
          );
          const billing = await chargeAITurn(game_id, token, aiMeta);
          emit({
            type: "done",
            action: "pass",
            ...passResult,
            billing,
            requested_model: requestedModelId,
            session_model: sessionModelId,
            response_model: aiResult?.response?.modelId,
            elapsed_ms: elapsedMs,
            candidates_found: candidates.length,
            timed_out: timedOut,
            auto_finalized: autoFinalized,
          });
          closeStream();
          return;
        }

        // Try the chosen placements; if rejected (invalid words), try next best
        let moveResult = await backendPost(
          `/api/game/${game_id}/ai-move/`,
          { placements: finalPlacements, ai_metadata: aiMeta },
          token,
        );

        if (!moveResult.ok) {
          const sortedValid = candidates
            .filter((c) => c.valid)
            .sort((a, b) => b.score - a.score);
          for (const alt of sortedValid) {
            if (JSON.stringify(alt.placements) === JSON.stringify(finalPlacements)) continue;
            moveResult = await backendPost(
              `/api/game/${game_id}/ai-move/`,
              { placements: alt.placements, ai_metadata: { ...aiMeta, fallback: true } },
              token,
            );
            if (moveResult.ok) break;
          }
        }

        if (!moveResult.ok) {
          const passResult = await backendPost(
            `/api/game/${game_id}/ai-pass/`,
            {},
            token,
          );
          const billing = await chargeAITurn(game_id, token, {
            ...aiMeta,
            fallback: true,
          });
          emit({
            type: "done",
            action: "pass",
            ...passResult,
            billing,
            reason: "no valid move accepted",
            requested_model: requestedModelId,
            session_model: sessionModelId,
            response_model: aiResult?.response?.modelId,
            elapsed_ms: elapsedMs,
            candidates_found: candidates.length,
            auto_finalized: autoFinalized,
          });
          closeStream();
          return;
        }

        const best = getBestCandidate();
        const appliedWords = Array.isArray(moveResult.words)
          ? (moveResult.words as Array<{ word?: string; score?: number }>)
          : [];
        const appliedWord = appliedWords[0]?.word ?? best?.word;
        const appliedScore = moveResult.points ?? appliedWords[0]?.score ?? best?.score;
        emit({
          type: "done",
          action: "place",
          ...moveResult,
          requested_model: requestedModelId,
          session_model: sessionModelId,
          response_model: aiResult?.response?.modelId,
          best_word: appliedWord,
          best_score: appliedScore,
          elapsed_ms: elapsedMs,
          candidates_found: candidates.length,
          timed_out: timedOut,
          auto_finalized: autoFinalized,
        });
      } catch (error) {
        const normalizedError = normalizeRouteError(error);
        if (normalizedError) {
          emit({
            type: "error",
            code: normalizedError.code,
            error: normalizedError.message,
          });
          closeStream();
          return;
        }

        console.error("AI move SSE error:", error);

        // Try to use best candidate even on error
        const best = candidates.filter((c) => c.valid).sort((a, b) => b.score - a.score)[0];
        if (best) {
          try {
            const moveResult = await backendPost(
              `/api/game/${game_id}/ai-move/`,
              { placements: best.placements, ai_metadata: { fallback: true } },
              token,
            );
            const appliedWords = Array.isArray(moveResult.words)
              ? (moveResult.words as Array<{ word?: string; score?: number }>)
              : [];
            emit({
              type: "done",
              action: "place",
              ...moveResult,
              best_word: appliedWords[0]?.word ?? best.word,
              best_score: moveResult.points ?? appliedWords[0]?.score ?? best.score,
              fallback: true,
            });
          } catch {
            emit({
              type: "error",
              error: error instanceof Error ? error.message : "AI move failed",
            });
          }
        } else {
          emit({
            type: "error",
            error:
              error instanceof Error
                ? error.message
                : "AI move failed",
          });
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
