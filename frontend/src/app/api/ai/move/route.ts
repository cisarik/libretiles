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
import { getModel } from "@/lib/ai-gateway";
import { MOVE_SYSTEM_PROMPT, buildMoveUserPrompt } from "@/lib/prompts";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const DEFAULT_TIMEOUT_S = 30;
const MAX_STEPS = 30;
const AUTO_FINALIZE_GRACE_MS = 2500;
const AUTO_FINALIZE_VALID_CAP = 4;

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

function sseEvent(data: Record<string, unknown>): string {
  return `data: ${JSON.stringify(data)}\n\n`;
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { game_id, token, model_id, timeout } = body as {
    game_id: string;
    token: string;
    model_id?: string;
    timeout?: number;
  };

  const timeoutS = Math.max(15, Math.min(timeout ?? DEFAULT_TIMEOUT_S, 600));
  const startTime = Date.now();

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
              auto_finalize_ms: AUTO_FINALIZE_GRACE_MS,
              valid_candidates: validCount,
            });

            if (validCount >= AUTO_FINALIZE_VALID_CAP) {
              autoFinalized = true;
              abortController.abort();
            } else {
              autoFinalizeTimer = setTimeout(() => {
                autoFinalized = true;
                abortController.abort();
              }, AUTO_FINALIZE_GRACE_MS);
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

        const model = getModel(model_id);
        const resolvedModelId =
          model_id ||
          process.env.NEXT_PUBLIC_DEFAULT_MODEL ||
          "openai/gpt-4o-mini";

        emit({
          type: "thinking",
          model: resolvedModelId,
          timeout: timeoutS,
        });
        emit({
          type: "thinking",
          status: "searching",
          message: "Exploring legal words and validating the board...",
        });

        // 2. Race: generateText vs timeout
        const timeoutId = setTimeout(() => {
          abortController.abort();
        }, timeoutS * 1000);

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let aiResult: any = null;
        let timedOut = false;

        try {
          aiResult = await Promise.race([
            generateText({
              model,
              maxOutputTokens: 4000,
              temperature: 0.3,
              system: MOVE_SYSTEM_PROMPT,
              prompt: buildMoveUserPrompt(context),
              abortSignal: abortController.signal,
              tools: {
                validateMove: tool({
                  description:
                    "Validate a proposed tile placement on the board. Returns " +
                    "legality, all words formed, per-word scores, and total score. " +
                    "Call this BEFORE finalizing any move.",
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
                    "(2019) English dictionary (279,496 words).",
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
              stopWhen: stepCountIs(MAX_STEPS),
            }),
            new Promise<never>((_, reject) => {
              abortController.signal.addEventListener("abort", () => {
                reject(new DOMException("Timeout", "AbortError"));
              });
            }),
          ]);
        } catch (err) {
          if (
            err instanceof DOMException &&
            err.name === "AbortError"
          ) {
            timedOut = true;
          } else {
            throw err;
          }
        } finally {
          clearTimeout(timeoutId);
          clearAutoFinalizeTimer();
        }

        // 3. Determine final move
        const elapsedMs = Date.now() - startTime;
        let finalPlacements: PlacementData[] = [];
        let finalAction = "place";

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

              if (parsed.exchange_letters && finalAction === "exchange") {
                const exchangeResult = await backendPost(
                  `/api/game/${game_id}/exchange/`,
                  { slot: 1, letters: parsed.exchange_letters },
                  token,
                );
                emit({
                  type: "done",
                  action: "exchange",
                  ...exchangeResult,
                  elapsed_ms: elapsedMs,
                  candidates_found: candidates.length,
                });
                controller.close();
                return;
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

        // 4. Apply the final move
        if (
          finalPlacements.length === 0 ||
          finalAction === "pass"
        ) {
          const passResult = await backendPost(
            `/api/game/${game_id}/pass/`,
            { slot: 1 },
            token,
          );
          emit({
            type: "done",
            action: "pass",
            ...passResult,
            elapsed_ms: elapsedMs,
            candidates_found: candidates.length,
            timed_out: timedOut,
            auto_finalized: autoFinalized,
          });
          controller.close();
          return;
        }

        const aiMeta = {
          model: resolvedModelId,
          usage: aiResult?.usage,
          steps: aiResult?.steps?.length ?? 0,
          elapsed_ms: elapsedMs,
          candidates_found: candidates.length,
          best_score: bestScore,
          timed_out: timedOut,
          auto_finalized: autoFinalized,
          tool_calls_count:
            aiResult?.steps?.reduce(
              (sum: number, s: { toolCalls: unknown[] }) =>
                sum + s.toolCalls.length,
              0,
            ) ?? 0,
        };

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
          emit({
            type: "done",
            action: "pass",
            ...passResult,
            reason: "no valid move accepted",
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
          best_word: appliedWord,
          best_score: appliedScore,
          elapsed_ms: elapsedMs,
          candidates_found: candidates.length,
          timed_out: timedOut,
          auto_finalized: autoFinalized,
        });
      } catch (error) {
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
