/**
 * Admin catalog probe wrapper around probeProviderCapability.
 *
 * Fake mode never constructs a runtime or touches the network. Live mode is
 * independently gated by PROVIDER_PROBE_LIVE === "1" and a hard outbound cap.
 */

import type { ProviderCapabilityStatus } from "./provider-capability";

export const ADMIN_PROBE_PROTOCOL_VERSION = 1;
export const ADMIN_PROBE_MAX_HTTP_DISPATCHES = 4;
export const ADMIN_PROBE_CAPABILITY_DEADLINE_MS = 20_000;
export const ADMIN_PROBE_WATCHDOG_MS = 22_000;
export const ADMIN_PROBE_LIVE_SENTINEL = "PROVIDER_PROBE_LIVE";
export const ADMIN_PROBE_MAX_INPUT_BYTES = 4096;
export const ADMIN_PROBE_MAX_OUTPUT_BYTES = 16_384;

export const ADMIN_PROBE_REASON_CODES = [
  "simulated",
  "incomplete",
  "live_disabled",
  "not_configured",
  "request_limit",
  "timeout",
  "worker_unavailable",
  "malformed_output",
  "pair_mismatch",
  "mode_mismatch",
  "capability",
  "throttled",
  "unknown",
] as const;

export type AdminProbeReasonCode = (typeof ADMIN_PROBE_REASON_CODES)[number];
export type AdminProbeMode = "fake" | "live";

export type AdminProbeCommand = Readonly<{
  version: number;
  mode: AdminProbeMode;
  provider: string;
  model: string;
}>;

export type AdminProbeResponse = Readonly<{
  version: number;
  executed_runtime_mode: AdminProbeMode;
  provider: string;
  model: string;
  status: ProviderCapabilityStatus;
  latency_ms: number | null;
  outbound_count: number | null;
  reason_code: AdminProbeReasonCode;
}>;

class RequestLimitError extends Error {
  constructor() {
    super("request_limit");
    this.name = "RequestLimitError";
  }
}

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

export function parseAdminProbeCommand(raw: string): AdminProbeCommand {
  if (utf8ByteLength(raw) > ADMIN_PROBE_MAX_INPUT_BYTES) {
    throw new Error("malformed_output");
  }
  const payload = JSON.parse(raw) as unknown;
  if (
    typeof payload !== "object" ||
    payload === null ||
    Array.isArray(payload)
  ) {
    throw new Error("malformed_output");
  }
  const record = payload as Record<string, unknown>;
  const allowed = new Set(["version", "mode", "provider", "model"]);
  for (const key of Object.keys(record)) {
    if (!allowed.has(key)) {
      throw new Error("malformed_output");
    }
  }
  if (record.version !== ADMIN_PROBE_PROTOCOL_VERSION) {
    throw new Error("malformed_output");
  }
  if (record.mode !== "fake" && record.mode !== "live") {
    throw new Error("malformed_output");
  }
  if (typeof record.provider !== "string" || typeof record.model !== "string") {
    throw new Error("malformed_output");
  }
  return {
    version: ADMIN_PROBE_PROTOCOL_VERSION,
    mode: record.mode,
    provider: record.provider,
    model: record.model,
  };
}

export function installAdminProbeFetchGuard(limit = ADMIN_PROBE_MAX_HTTP_DISPATCHES): {
  restore: () => void;
  dispatched: () => number;
  limited: () => boolean;
} {
  const original = globalThis.fetch;
  let dispatched = 0;
  let limited = false;
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    if (dispatched >= limit) {
      limited = true;
      return Promise.reject(new RequestLimitError());
    }
    dispatched += 1;
    return original(input, init);
  }) as typeof fetch;
  return {
    restore: () => {
      globalThis.fetch = original;
    },
    dispatched: () => dispatched,
    limited: () => limited,
  };
}

export async function runAdminProviderProbe(
  command: AdminProbeCommand,
  env: Record<string, string | undefined> = process.env,
): Promise<AdminProbeResponse> {
  if (command.mode !== "live") {
    return {
      version: ADMIN_PROBE_PROTOCOL_VERSION,
      executed_runtime_mode: "fake",
      provider: command.provider,
      model: command.model,
      status: "pass",
      latency_ms: 0,
      outbound_count: 0,
      reason_code: "simulated",
    };
  }

  if (env[ADMIN_PROBE_LIVE_SENTINEL] !== "1") {
    return {
      version: ADMIN_PROBE_PROTOCOL_VERSION,
      executed_runtime_mode: "live",
      provider: command.provider,
      model: command.model,
      status: "unknown",
      latency_ms: 0,
      outbound_count: 0,
      reason_code: "live_disabled",
    };
  }

  const { probeProviderCapability } = await import("./provider-capability");
  const guard = installAdminProbeFetchGuard();
  try {
    const result = await probeProviderCapability({
      provider: command.provider,
      model: command.model,
      timeout_ms: ADMIN_PROBE_CAPABILITY_DEADLINE_MS,
    });
    if (result.provider !== command.provider || result.model !== command.model) {
      return {
        version: ADMIN_PROBE_PROTOCOL_VERSION,
        executed_runtime_mode: "live",
        provider: command.provider,
        model: command.model,
        status: "unknown",
        latency_ms: result.latency_ms,
        outbound_count: guard.dispatched(),
        reason_code: "pair_mismatch",
      };
    }
    if (guard.limited()) {
      return {
        version: ADMIN_PROBE_PROTOCOL_VERSION,
        executed_runtime_mode: "live",
        provider: command.provider,
        model: command.model,
        status: "unknown",
        latency_ms: result.latency_ms,
        outbound_count: guard.dispatched(),
        reason_code: "request_limit",
      };
    }
    return {
      version: ADMIN_PROBE_PROTOCOL_VERSION,
      executed_runtime_mode: "live",
      provider: command.provider,
      model: command.model,
      status: result.status,
      latency_ms: result.latency_ms,
      outbound_count: guard.dispatched(),
      reason_code:
        result.status === "not_configured" ? "not_configured" : "capability",
    };
  } catch (error) {
    const limited = guard.limited();
    const timedOut =
      error instanceof Error &&
      (error.name === "TimeoutError" || error.name === "AbortError");
    return {
      version: ADMIN_PROBE_PROTOCOL_VERSION,
      executed_runtime_mode: "live",
      provider: command.provider,
      model: command.model,
      status: timedOut ? "timeout" : limited ? "unknown" : "unknown",
      latency_ms: null,
      outbound_count: limited || guard.dispatched() > 0 ? guard.dispatched() : null,
      reason_code: limited ? "request_limit" : timedOut ? "timeout" : "unknown",
    };
  } finally {
    guard.restore();
  }
}
