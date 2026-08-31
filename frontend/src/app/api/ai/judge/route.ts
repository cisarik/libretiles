/**
 * AI Word Judge API Route (Tier 3 validation)
 *
 * Used as a fallback when a word is not in the local Collins 2019 dictionary.
 * The AI acts as a Libre Tiles referee, judging whether words are valid
 * based on lexicon knowledge. Collins 2019 remains the persisted-move
 * authority; a judge result never overrides it.
 *
 * Validation pipeline:
 *   Tier 1: Local Collins 2019 dictionary (279,496 words, O(1) lookup) — Django
 *   Tier 2: Online dictionary API (optional) — Django
 *   Tier 3: AI Judge (this route) — newest-first free-rival fallback queue
 *
 * Fallback contract:
 *   - Same shared queue builder as /api/ai/move (preference first, then
 *     untouched catalog order), capped at three distinct pairs.
 *   - At most three sequential provider lanes, 10s per attempt, 30s overall.
 *   - AI SDK retries disabled; malformed output advances to the next model.
 *   - Exhaustion is an explicit HTTP 503 — malformed output is never
 *     synthesized into false "invalid" results.
 */

import { NextRequest, NextResponse } from "next/server";
import { generateText } from "ai";
import { buildFallbackQueue, MAX_FALLBACK_ATTEMPTS } from "@/lib/ai-fallback";
import {
  bearerTokenFromAuthorizationHeader,
  verifyUserBearerToken,
  type TokenVerificationResult,
} from "@/lib/api-auth";
import {
  getLanguageRuntime,
  parseCatalogModelRows,
  type ProviderRequestTracker,
} from "@/lib/ai-runtimes";
import { judgePromptSpecFromBody, judgeSystemPromptFor } from "@/lib/prompts";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const ATTEMPT_TIMEOUT_MS = 10_000;
const OVERALL_BUDGET_MS = 30_000;
const MAX_TRACKED_REQUESTS = 50_000;
const MAX_TRACKED_TOKENS = 1_000_000_000;
const MAX_RETRY_AFTER_SECONDS = 86_400;
/**
 * Prompt-stuffing caps. A 15×15 Scrabble placement forms at most eight words,
 * each at most 15 letters. 12 words leaves modest headroom without allowing
 * a bulk prompt-injection payload.
 */
const MAX_JUDGE_WORDS = 12;
const MAX_JUDGE_WORD_LENGTH = 15;

type JudgeResult = {
  results: Array<{ word: string; valid: boolean; reason?: string }>;
};

type JudgeAccounting = {
  providerRequests: number;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  hasUsage: boolean;
  retryAfterSeconds?: number;
};

function boundedInteger(value: unknown, maximum: number): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? Math.min(Math.floor(value), maximum)
    : null;
}

function addTrackerSnapshot(
  accounting: JudgeAccounting,
  tracker: ProviderRequestTracker,
): void {
  const snapshot = tracker.snapshot();
  accounting.providerRequests = Math.min(
    accounting.providerRequests +
      (boundedInteger(snapshot.provider_requests, MAX_TRACKED_REQUESTS) ?? 0),
    MAX_TRACKED_REQUESTS,
  );
  if (snapshot.usage) {
    accounting.hasUsage = true;
    accounting.inputTokens = Math.min(
      accounting.inputTokens +
        (boundedInteger(snapshot.usage.input_tokens, MAX_TRACKED_TOKENS) ?? 0),
      MAX_TRACKED_TOKENS,
    );
    accounting.outputTokens = Math.min(
      accounting.outputTokens +
        (boundedInteger(snapshot.usage.output_tokens, MAX_TRACKED_TOKENS) ?? 0),
      MAX_TRACKED_TOKENS,
    );
    accounting.totalTokens = Math.min(
      accounting.totalTokens +
        (boundedInteger(snapshot.usage.total_tokens, MAX_TRACKED_TOKENS) ?? 0),
      MAX_TRACKED_TOKENS,
    );
  }
  if (snapshot.retry_after_seconds !== undefined) {
    const retryAfterSeconds = boundedInteger(
      snapshot.retry_after_seconds,
      MAX_RETRY_AFTER_SECONDS,
    );
    if (retryAfterSeconds !== null) {
      accounting.retryAfterSeconds = Math.max(
        accounting.retryAfterSeconds ?? 0,
        retryAfterSeconds,
      );
    }
  }
}

function accountingFields(accounting: JudgeAccounting) {
  return {
    provider_requests_used: accounting.providerRequests,
    ...(accounting.hasUsage
      ? {
          usage: {
            input_tokens: accounting.inputTokens,
            output_tokens: accounting.outputTokens,
            total_tokens: accounting.totalTokens,
          },
        }
      : {}),
    ...(accounting.retryAfterSeconds === undefined
      ? {}
      : { retry_after_seconds: accounting.retryAfterSeconds }),
  };
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

function normalizeWord(value: unknown): string | null {
  return typeof value === "string" ? value.trim().toUpperCase() : null;
}

/**
 * Strict one-result-per-input validation: the payload must be an object with
 * a `results` array covering exactly the requested words (order-insensitive,
 * case-insensitive), each with a boolean `valid`. Anything else is invalid
 * judge output and must not be surfaced as a verdict.
 */
function parseJudgeResults(
  text: string,
  words: string[],
): JudgeResult | null {
  const match = text.match(/\{[\s\S]*"results"[\s\S]*\}/);
  if (!match) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(match[0]);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return null;
  }
  const rawResults = (parsed as Record<string, unknown>).results;
  if (!Array.isArray(rawResults)) return null;
  if (rawResults.length !== words.length) return null;

  const expected = new Map<string, number>();
  for (const word of words) {
    expected.set(word, (expected.get(word) ?? 0) + 1);
  }

  const results: JudgeResult["results"] = [];
  for (const entry of rawResults) {
    if (typeof entry !== "object" || entry === null) return null;
    const record = entry as Record<string, unknown>;
    const word = normalizeWord(record.word);
    if (!word || typeof record.valid !== "boolean") return null;
    if ((expected.get(word) ?? 0) < 1) return null;
    expected.set(word, (expected.get(word) ?? 0) - 1);
    results.push({
      word,
      valid: record.valid,
      ...(typeof record.reason === "string" ? { reason: record.reason } : {}),
    });
  }
  for (const count of expected.values()) {
    if (count !== 0) return null;
  }
  return { results };
}

function verificationFailureResponse(
  result: Extract<TokenVerificationResult, { ok: false }>,
) {
  if (result.status === 401) {
    return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  }
  if (result.status === 429) {
    return NextResponse.json(
      { error: "Too many requests" },
      {
        status: 429,
        ...(result.retryAfter
          ? { headers: { "Retry-After": result.retryAfter } }
          : {}),
      },
    );
  }
  return NextResponse.json({ error: "AI judge failed" }, { status: 503 });
}

export async function POST(req: NextRequest) {
  const token = bearerTokenFromAuthorizationHeader(
    req.headers.get("authorization"),
  );
  if (!token) {
    return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  }

  const verification = await verifyUserBearerToken(token);
  if (!verification.ok) {
    return verificationFailureResponse(verification);
  }

  let body: {
    words?: unknown;
    model_id?: unknown;
    lexicon_id?: unknown;
    variant?: unknown;
  };
  try {
    body = (await req.json()) as {
      words?: unknown;
      model_id?: unknown;
      lexicon_id?: unknown;
      variant?: unknown;
    };
  } catch {
    return NextResponse.json({ error: "No words provided" }, { status: 400 });
  }

  const rawWords = body.words;
  if (
    !Array.isArray(rawWords) ||
    rawWords.length === 0 ||
    rawWords.some((word) => typeof word !== "string" || word.trim().length === 0)
  ) {
    return NextResponse.json({ error: "No words provided" }, { status: 400 });
  }
  const words = rawWords.map((word) => word.trim().toUpperCase());
  if (words.length > MAX_JUDGE_WORDS) {
    return NextResponse.json({ error: "Too many words" }, { status: 400 });
  }
  if (words.some((word) => word.length > MAX_JUDGE_WORD_LENGTH)) {
    return NextResponse.json({ error: "Word too long" }, { status: 400 });
  }
  const judgeSpec = judgePromptSpecFromBody(body);

  const catalogRows = await fetchCatalogModelRows();
  if (!catalogRows || catalogRows.length === 0) {
    return NextResponse.json({ error: "AI judge failed" }, { status: 503 });
  }

  const preferenceId =
    typeof body.model_id === "string" && body.model_id ? body.model_id : "";
  const queue = buildFallbackQueue(preferenceId, catalogRows);
  if (queue.length === 0) {
    return NextResponse.json({ error: "AI judge failed" }, { status: 503 });
  }

  const overallDeadlineMs = Date.now() + OVERALL_BUDGET_MS;
  const accounting: JudgeAccounting = {
    providerRequests: 0,
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    hasUsage: false,
  };
  for (const pair of queue.slice(0, MAX_FALLBACK_ATTEMPTS)) {
    if (overallDeadlineMs - Date.now() <= 0) break;

    let runtime;
    try {
      runtime = await getLanguageRuntime(pair.provider, pair.model_id);
    } catch {
      continue;
    }

    const remainingMs = Math.floor(overallDeadlineMs - Date.now());
    if (remainingMs <= 0) {
      addTrackerSnapshot(accounting, runtime.tracker);
      break;
    }
    const attemptTimeoutMs = Math.max(
      1,
      Math.min(ATTEMPT_TIMEOUT_MS, remainingMs),
    );

    let parsed: JudgeResult | null = null;
    try {
      const result = await generateText({
        model: runtime.model,
        maxOutputTokens: 1000,
        temperature: 0.1,
        maxRetries: 0,
        abortSignal: AbortSignal.timeout(attemptTimeoutMs),
        system: judgeSystemPromptFor(judgeSpec),
        prompt: `Validate these words for ${judgeSpec.language} Libre Tiles play: ${words.join(", ")}. Return JSON exactly matching the schema.`,
      });

      runtime.tracker.recordUsage(result.usage);
      parsed = parseJudgeResults(result.text, words);
    } catch {
      // Timeout, provider failure, or SDK error — advance to the next model.
    }
    addTrackerSnapshot(accounting, runtime.tracker);
    if (parsed) {
      return NextResponse.json({
        ...parsed,
        model: pair.model_id,
        provider: pair.provider,
        ...accountingFields(accounting),
      });
    }
  }

  return NextResponse.json(
    { error: "AI judge failed", ...accountingFields(accounting) },
    { status: 503 },
  );
}
