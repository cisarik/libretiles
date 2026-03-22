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
  isGatewayConfigured,
} from "@/lib/ai-gateway";
import { MOVE_SYSTEM_PROMPT, buildMoveUserPrompt } from "@/lib/prompts";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const DEFAULT_TIMEOUT_S = 30;
const DEFAULT_MAX_STEPS = 30;
const MIN_STEPS = 5;
const MAX_STEPS = 100;
const DEFAULT_MAX_OUTPUT_TOKENS = 10000;
const MIN_MAX_OUTPUT_TOKENS = 2000;
const MAX_MAX_OUTPUT_TOKENS = 64000;
const AUTO_FINALIZE_GRACE_MS = 2500;
const AUTO_FINALIZE_VALID_CAP = 4;
const EXTENDED_AUTO_FINALIZE_GRACE_MS = 6000;
const EXTENDED_AUTO_FINALIZE_VALID_CAP = 7;

async function backendPost(path: string, body: unknown, token: string) {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function backendGet(path: string, token: string) {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.json();
}

async function backendPatch(path: string, body: unknown, token: string) {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "PATCH",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  return res.json();
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

      function emit(data: Record<string, unknown>) {
        try {
          controller.enqueue(encoder.encode(sseEvent(data)));
        } catch {
          // stream may have been closed by the client
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
            controller.close();
            return;
          }
        }

        const profile = await backendGet("/api/auth/me/", token).catch(() => null);
        const availableCredits =
          typeof profile?.credit_balance === "string"
            ? Number.parseFloat(profile.credit_balance)
            : Number.NaN;

        if (Number.isFinite(availableCredits) && availableCredits <= 0) {
          emit({
            type: "error",
            code: "insufficient_user_credit",
            error:
              "Your credit balance is empty. Open settings to top up credit or switch to a cheaper AI model.",
            credit_balance: profile.credit_balance,
          });
          controller.close();
          return;
        }

        // 1. Fetch game context
        const context = await backendGet(
          `/api/game/${game_id}/ai-context/`,
          token,
        );

        if (!context.compact_state) {
          emit({ type: "error", error: "Could not fetch game context" });
          controller.close();
          return;
        }

        const sessionModelId =
          typeof context.ai_model_id === "string" ? context.ai_model_id : null;
        const backendMaxOutputTokens =
          typeof context.ai_move_max_output_tokens === "number"
            ? context.ai_move_max_output_tokens
            : Number.parseInt(String(context.ai_move_max_output_tokens ?? ""), 10);
        const maxOutputTokens = Number.isFinite(backendMaxOutputTokens)
          ? clampNumber(
              backendMaxOutputTokens,
              MIN_MAX_OUTPUT_TOKENS,
              MAX_MAX_OUTPUT_TOKENS,
            )
          : DEFAULT_MAX_OUTPUT_TOKENS;
        const useExtendedSearchBudget = timeoutS >= 90 || maxSteps >= 45;
        autoFinalizeGraceMs = useExtendedSearchBudget
          ? EXTENDED_AUTO_FINALIZE_GRACE_MS
          : AUTO_FINALIZE_GRACE_MS;
        autoFinalizeValidCap = useExtendedSearchBudget
          ? EXTENDED_AUTO_FINALIZE_VALID_CAP
          : AUTO_FINALIZE_VALID_CAP;
        const resolvedModelId =
          requestedModelId ||
          sessionModelId ||
          process.env.NEXT_PUBLIC_DEFAULT_MODEL ||
          "openai/gpt-5.4";
        const model = getModel(resolvedModelId);
        let providerPath =
          isGatewayConfigured() && !canUseDirectOpenAIModel(resolvedModelId)
            ? "gateway"
            : isGatewayConfigured()
              ? "gateway"
              : "direct_openai";
        let gatewayFallbackUsed = false;

        emit({
          type: "thinking",
          model: resolvedModelId,
          timeout: timeoutS,
          max_steps: maxSteps,
          max_output_tokens: maxOutputTokens,
          provider_path: providerPath,
        });
        emit({
          type: "thinking",
          status: "searching",
          message: "Exploring legal words and validating the board...",
        });

        const runGeneration = (activeModel: ReturnType<typeof getModel>) =>
          Promise.race([
            generateText({
              model: activeModel,
              maxOutputTokens,
              temperature: 0.15,
              system: MOVE_SYSTEM_PROMPT,
              prompt: buildMoveUserPrompt(context),
              abortSignal: abortController.signal,
              tools: {
                validateMove: tool({
                  description:
                    "Validate a proposed tile placement on the board. Returns " +
                    "legality, all words formed, per-word scores, and total score. " +
                    "Call this BEFORE finalizing any move. Only use it for " +
                    "high-confidence English candidates, not random dictionary guesses.",
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
                    "to confirm words formed by a legal placement, never to brainstorm random strings.",
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
          aiResult = await runGeneration(model);
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
          try {
            const jsonMatch = aiResult.text.match(
              /\{[\s\S]*?"action"[\s\S]*?\}/,
            );
            if (jsonMatch) {
              const parsed = JSON.parse(jsonMatch[0]);
              finalAction = parsed.action || "place";

              if (
                parsed.placements &&
                Array.isArray(parsed.placements)
              ) {
                finalPlacements = parsed.placements;
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
          } catch {
            // JSON parse failed
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
          provider_path: providerPath,
          gateway_fallback_used: gatewayFallbackUsed,
          max_output_tokens: maxOutputTokens,
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
            `/api/game/${game_id}/exchange/`,
            { slot: 1, letters: exchangeLetters },
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
          controller.close();
          return;
        }

        if (finalPlacements.length === 0 || finalAction === "pass") {
          const passResult = await backendPost(
            `/api/game/${game_id}/pass/`,
            { slot: 1 },
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
          controller.close();
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
            `/api/game/${game_id}/pass/`,
            { slot: 1 },
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
          controller.close();
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
          try {
            controller.close();
          } catch {
            // already closed
          }
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
        try {
          controller.close();
        } catch {
          // already closed
        }
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
