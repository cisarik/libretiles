/**
 * Server-only, explicit provider capability probe.
 *
 * This module is deliberately not imported by application boot, catalog, or
 * gameplay paths. The opt-in live Vitest entry point is its only operational
 * caller. It exercises the same runtime factory and generateText loop as a
 * real AI turn while returning only bounded, non-sensitive telemetry.
 */

import { generateText, tool, type LanguageModel, type StopCondition } from "ai";
import { z } from "zod";
import { getLanguageRuntime } from "./ai-runtimes";
import {
  EXACT_PROVIDER_METADATA,
  OPENROUTER_PROVIDER,
  isValidRuntimePair,
} from "./provider-registry";
import type { ProviderRequestTracker } from "./openai-compatible";

const MAX_PROBE_LATENCY_MS = 300_000;
const MAX_PROBE_OUTBOUND_COUNT = 10_000;
const DEFAULT_PROBE_TIMEOUT_MS = 30_000;
const MIN_PROBE_TIMEOUT_MS = 1;
const MAX_PROBE_TIMEOUT_MS = 60_000;
const INVALID_OUTPUT_VALUE = "invalid";
const MISSING_OUTPUT_VALUE = "not_configured";

export const PROVIDER_CAPABILITY_STATUSES = [
  "pass",
  "not_configured",
  "auth_failed",
  "rate_limited",
  "model_unavailable",
  "named_tool_unsupported",
  "tool_continuation_failed",
  "schema_failed",
  "timeout",
  "unknown",
] as const;

export type ProviderCapabilityStatus =
  (typeof PROVIDER_CAPABILITY_STATUSES)[number];

export type ProviderCapabilityResult = Readonly<{
  provider: string;
  model: string;
  status: ProviderCapabilityStatus;
  latency_ms: number;
  outbound_count: number;
}>;

export type ProviderCapabilityProbeInput = Readonly<{
  provider?: string;
  model?: string;
  timeout_ms?: number;
}>;

type Placement = Readonly<{ row: number; col: number; letter: string }>;

export const PROVIDER_CAPABILITY_PLACEMENTS = [
  { row: 7, col: 4, letter: "R" },
  { row: 7, col: 5, letter: "E" },
  { row: 7, col: 6, letter: "T" },
  { row: 7, col: 7, letter: "A" },
  { row: 7, col: 8, letter: "I" },
  { row: 7, col: 9, letter: "N" },
  { row: 7, col: 10, letter: "S" },
] as const satisfies readonly Placement[];

class ProbeSchemaError extends Error {
  constructor() {
    super("probe_schema_failed");
    this.name = "ProbeSchemaError";
  }
}

class ProbeContinuationError extends Error {
  constructor() {
    super("probe_tool_continuation_failed");
    this.name = "ProbeContinuationError";
  }
}

class ProbeTimeoutError extends Error {
  constructor() {
    super("probe_timeout");
    this.name = "ProbeTimeoutError";
  }
}

function boundedInteger(value: unknown, maximum: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return 0;
  }
  return Math.min(Math.floor(value), maximum);
}

function boundedTimeout(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_PROBE_TIMEOUT_MS;
  }
  return Math.min(
    Math.max(Math.floor(value), MIN_PROBE_TIMEOUT_MS),
    MAX_PROBE_TIMEOUT_MS,
  );
}

function safeResult(
  provider: string,
  model: string,
  status: ProviderCapabilityStatus,
  startedAtMs: number,
  tracker?: ProviderRequestTracker,
): ProviderCapabilityResult {
  return {
    provider,
    model,
    status,
    latency_ms: boundedInteger(Date.now() - startedAtMs, MAX_PROBE_LATENCY_MS),
    outbound_count: boundedInteger(
      tracker?.snapshot().provider_requests ?? 0,
      MAX_PROBE_OUTBOUND_COUNT,
    ),
  };
}

function resolvePair(input: ProviderCapabilityProbeInput):
  | { ok: true; provider: string; model: string }
  | { ok: false; provider: string; model: string } {
  const provider = input.provider?.trim() ?? "";
  const explicitModel = input.model?.trim() ?? "";
  if (!provider) {
    return {
      ok: false,
      provider: MISSING_OUTPUT_VALUE,
      model: MISSING_OUTPUT_VALUE,
    };
  }

  if (provider === OPENROUTER_PROVIDER) {
    if (
      !explicitModel ||
      explicitModel.length > 200 ||
      !/^[A-Za-z0-9_.@-]+\/[A-Za-z0-9_.@:-]+:free$/.test(explicitModel) ||
      !isValidRuntimePair(provider, explicitModel)
    ) {
      return {
        ok: false,
        provider: OPENROUTER_PROVIDER,
        model: explicitModel ? INVALID_OUTPUT_VALUE : MISSING_OUTPUT_VALUE,
      };
    }
    return { ok: true, provider, model: explicitModel };
  }

  const providerRows = EXACT_PROVIDER_METADATA.filter(
    (entry) => entry.provider === provider,
  );
  if (providerRows.length !== 1) {
    return {
      ok: false,
      provider: INVALID_OUTPUT_VALUE,
      model: INVALID_OUTPUT_VALUE,
    };
  }

  const model = explicitModel || providerRows[0].model_id;
  if (!isValidRuntimePair(provider, model)) {
    return { ok: false, provider, model: INVALID_OUTPUT_VALUE };
  }
  return { ok: true, provider, model };
}

function placementsMatch(value: unknown): value is readonly Placement[] {
  if (!Array.isArray(value) || value.length !== PROVIDER_CAPABILITY_PLACEMENTS.length) {
    return false;
  }
  return PROVIDER_CAPABILITY_PLACEMENTS.every((expected, index) => {
    const actual = value[index];
    return (
      typeof actual === "object" &&
      actual !== null &&
      !Array.isArray(actual) &&
      Object.keys(actual).length === 3 &&
      (actual as Record<string, unknown>).row === expected.row &&
      (actual as Record<string, unknown>).col === expected.col &&
      (actual as Record<string, unknown>).letter === expected.letter
    );
  });
}

function exactPlacementSchema(row: number, col: number, letter: string) {
  return z
    .object({
      row: z.literal(row),
      col: z.literal(col),
      letter: z.literal(letter),
    })
    .strict();
}

type ErrorSignals = Readonly<{
  statuses: readonly number[];
  codes: readonly string[];
  names: readonly string[];
  message: string;
}>;

function collectErrorSignals(error: unknown): ErrorSignals {
  const statuses: number[] = [];
  const codes: string[] = [];
  const names: string[] = [];
  const messages: string[] = [];
  const seen = new Set<unknown>();

  function visit(node: unknown): void {
    if (node === null || node === undefined) return;
    if (typeof node === "string") {
      messages.push(node.toLowerCase());
      return;
    }
    if (typeof node !== "object" || seen.has(node)) return;
    seen.add(node);
    const record = node as Record<string, unknown>;
    if (typeof record.status === "number") statuses.push(record.status);
    if (typeof record.statusCode === "number") statuses.push(record.statusCode);
    if (typeof record.code === "string") codes.push(record.code.toLowerCase());
    if (typeof record.name === "string") names.push(record.name.toLowerCase());
    if (typeof record.message === "string") {
      messages.push(record.message.toLowerCase());
    }
    visit(record.cause);
    visit(record.lastError);
    if (Array.isArray(record.errors)) record.errors.forEach(visit);
  }

  visit(error);
  return { statuses, codes, names, message: messages.join(" ") };
}

function classifyError(
  error: unknown,
  tracker: ProviderRequestTracker | undefined,
  validateSucceeded: boolean,
): ProviderCapabilityStatus {
  if (error instanceof ProbeTimeoutError) return "timeout";
  if (error instanceof ProbeSchemaError) return "schema_failed";
  if (error instanceof ProbeContinuationError) {
    return "tool_continuation_failed";
  }

  const signals = collectErrorSignals(error);
  const outbound = tracker?.snapshot().provider_requests ?? 0;
  const hasName = (value: string) => signals.names.includes(value);
  const hasCode = (value: string) => signals.codes.includes(value);
  const mentions = (value: string) => signals.message.includes(value);

  if (
    hasName("aborterror") ||
    hasName("timeouterror") ||
    hasCode("etimedout") ||
    hasCode("abort_err") ||
    mentions("timed out") ||
    mentions("timeout")
  ) {
    return "timeout";
  }

  if (
    hasName("ai_invalidtoolinputerror") ||
    hasName("ai_nosuchtoolerror") ||
    hasCode("ai_invalid_tool_input") ||
    hasCode("ai_no_such_tool") ||
    mentions("invalid tool input") ||
    mentions("tool input schema") ||
    mentions("schema validation")
  ) {
    return "schema_failed";
  }

  if (
    signals.statuses.includes(429) ||
    hasCode("provider_rate_limited") ||
    hasCode("resource_exhausted") ||
    mentions("rate limit") ||
    mentions("too many requests") ||
    mentions("resource exhausted")
  ) {
    return "rate_limited";
  }

  if (
    signals.statuses.includes(401) ||
    signals.statuses.includes(403) ||
    hasCode("provider_auth_failed") ||
    mentions("invalid api key") ||
    mentions("authentication failed") ||
    mentions("unauthorized") ||
    mentions("forbidden")
  ) {
    return outbound === 0 ? "not_configured" : "auth_failed";
  }

  if (
    (mentions("unsupported") &&
      (mentions("tool_choice") ||
        mentions("tool choice") ||
        mentions("function calling") ||
        mentions("tool use"))) ||
    mentions("named tool") ||
    hasCode("unsupported_tools")
  ) {
    return "named_tool_unsupported";
  }

  if (
    signals.statuses.includes(404) ||
    hasCode("provider_unavailable") ||
    hasCode("model_not_found") ||
    mentions("no endpoints found") ||
    mentions("model unavailable") ||
    mentions("model is unavailable") ||
    mentions("model not found") ||
    mentions("deployment not found")
  ) {
    return "model_unavailable";
  }

  if (validateSucceeded) return "tool_continuation_failed";
  return "unknown";
}

/**
 * Run one exact-pair probe. All failures are converted to the five-field
 * sanitized result; provider errors never cross this boundary.
 */
export async function probeProviderCapability(
  input: ProviderCapabilityProbeInput,
): Promise<ProviderCapabilityResult> {
  const startedAtMs = Date.now();
  const pair = resolvePair(input);
  if (!pair.ok) {
    return safeResult(
      pair.provider,
      pair.model,
      "not_configured",
      startedAtMs,
    );
  }

  let tracker: ProviderRequestTracker | undefined;
  let model: LanguageModel;
  try {
    const runtime = await getLanguageRuntime(pair.provider, pair.model);
    model = runtime.model;
    tracker = runtime.tracker;
  } catch (error) {
    return safeResult(
      pair.provider,
      pair.model,
      classifyError(error, tracker, false),
      startedAtMs,
      tracker,
    );
  }

  const nonce = crypto.randomUUID();
  let validateSucceeded = false;
  let finishSucceeded = false;
  let stateMachineFailure: ProviderCapabilityStatus | null = null;

  function latchStateMachineFailure(
    status: "schema_failed" | "tool_continuation_failed",
  ): void {
    stateMachineFailure ??= status;
  }

  const tools = {
    validateMove: tool({
      description:
        "Validate exactly RETAINS across row 7, columns 4 through 10. " +
        "Use the seven placements exactly as specified by the schema.",
      inputSchema: z
        .object({
          placements: z.tuple([
            exactPlacementSchema(7, 4, "R"),
            exactPlacementSchema(7, 5, "E"),
            exactPlacementSchema(7, 6, "T"),
            exactPlacementSchema(7, 7, "A"),
            exactPlacementSchema(7, 8, "I"),
            exactPlacementSchema(7, 9, "N"),
            exactPlacementSchema(7, 10, "S"),
          ]),
        })
        .strict(),
      execute: async ({ placements }) => {
        if (validateSucceeded) {
          latchStateMachineFailure("tool_continuation_failed");
          throw new ProbeContinuationError();
        }
        if (!placementsMatch(placements)) {
          latchStateMachineFailure("schema_failed");
          throw new ProbeSchemaError();
        }
        validateSucceeded = true;
        return { valid: true as const, nonce };
      },
    }),
    finishMove: tool({
      description:
        "After validateMove returns valid:true and its nonce, finish the probe.",
      inputSchema: z.object({ ready: z.literal(true) }).strict(),
      execute: async ({ ready }) => {
        if (ready !== true) {
          latchStateMachineFailure("schema_failed");
          throw new ProbeSchemaError();
        }
        if (!validateSucceeded) {
          latchStateMachineFailure("tool_continuation_failed");
          throw new ProbeContinuationError();
        }
        finishSucceeded = true;
        return { ok: true as const };
      },
    }),
  };

  const stopWhen: StopCondition<typeof tools> = ({ steps }) =>
    finishSucceeded || stateMachineFailure !== null || steps.length >= 3;
  const abortController = new AbortController();
  const timeoutMs = boundedTimeout(input.timeout_ms);
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      abortController.abort();
      reject(new ProbeTimeoutError());
    }, timeoutMs);
  });

  try {
    const generation = await Promise.race([
      generateText({
        model,
        maxRetries: 0,
        abortSignal: abortController.signal,
        tools,
        prompt:
          "Capability ping: call validateMove with RETAINS at " +
          "(7,4,R),(7,5,E),(7,6,T),(7,7,A),(7,8,I),(7,9,N),(7,10,S). " +
          "After the tool returns valid:true and a nonce pong, call " +
          "finishMove with ready:true. Do not answer with prose.",
        prepareStep: ({ stepNumber }) =>
          stepNumber === 0
            ? {
                activeTools: ["validateMove"] as Array<keyof typeof tools>,
                toolChoice: {
                  type: "tool" as const,
                  toolName: "validateMove" as const,
                },
              }
            : {
                activeTools: ["validateMove", "finishMove"] as Array<
                  keyof typeof tools
                >,
                toolChoice: "auto" as const,
              },
        onStepFinish: (step) => {
          for (const call of step.toolCalls) {
            if (call.dynamic === true && call.invalid === true) {
              const classified = classifyError(
                call.error,
                tracker,
                validateSucceeded,
              );
              latchStateMachineFailure(
                classified === "tool_continuation_failed"
                  ? "tool_continuation_failed"
                  : "schema_failed",
              );
            }
          }
          for (const part of step.content) {
            if (part.type !== "tool-error") continue;
            const classified = classifyError(
              part.error,
              tracker,
              validateSucceeded,
            );
            latchStateMachineFailure(
              classified === "tool_continuation_failed"
                ? "tool_continuation_failed"
                : "schema_failed",
            );
          }
        },
        stopWhen,
      }),
      timeoutPromise,
    ]);
    tracker.recordUsage(generation.totalUsage ?? generation.usage);

    const status: ProviderCapabilityStatus =
      stateMachineFailure ??
      (finishSucceeded
        ? "pass"
        : validateSucceeded
          ? "tool_continuation_failed"
          : "named_tool_unsupported");
    return safeResult(pair.provider, pair.model, status, startedAtMs, tracker);
  } catch (error) {
    return safeResult(
      pair.provider,
      pair.model,
      abortController.signal.aborted
        ? "timeout"
        : classifyError(error, tracker, validateSucceeded),
      startedAtMs,
      tracker,
    );
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}
