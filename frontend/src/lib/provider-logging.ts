/**
 * Server-only provider-failure logging.
 *
 * This module is deliberately not client-safe: it must never be imported from
 * browser code, any `"use client"` module, `src/components/`, `src/hooks/`,
 * or an App Router page. Runtime call sites are Next.js API routes and other
 * server-only lib modules. Records go to the server log sink only; they are
 * not added to SSE payloads or `ai_metadata`.
 */

export const PROVIDER_FAILURE_MESSAGE_MAX_LENGTH = 200;

export type ProviderFailurePhase =
  | "runtime_construction"
  | "provider_http"
  | "provider_transport"
  | "generate_text";

export type ProviderFailureRecord = {
  readonly provider: string;
  readonly phase: ProviderFailurePhase;
  readonly status: number | null;
  readonly errorClass: string;
  readonly message: string;
};

const CREDENTIAL_PREFIX_PATTERN =
  /\b(?:sk-or-|sk-|nvapi-|gsk_|AIza|hf_|whsec_|xox[baprs]-)[A-Za-z0-9_\-]+/g;
const BEARER_PATTERN = /Bearer\s+\S+/gi;
const HIGH_ENTROPY_RUN = /[A-Za-z0-9+/=_\-]{24,}/g;

function entropyRatio(value: string): number {
  if (!value) return 0;
  return new Set(value).size / value.length;
}

function redactCredentialMaterial(message: string): string {
  let out = message.replace(BEARER_PATTERN, "Bearer [redacted]");
  out = out.replace(CREDENTIAL_PREFIX_PATTERN, "[redacted]");
  out = out.replace(HIGH_ENTROPY_RUN, (run) => {
    if (run.includes("[redacted]")) return run;
    return entropyRatio(run) >= 0.35 && new Set(run).size >= 10
      ? "[redacted]"
      : run;
  });
  return out;
}

function errorClassName(error: unknown): string {
  if (error instanceof Error) {
    return error.name || error.constructor.name;
  }
  return typeof error;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

export function recordProviderFailure(input: {
  provider: string;
  phase: ProviderFailurePhase;
  status?: number | null;
  error: unknown;
}): ProviderFailureRecord {
  const redacted = redactCredentialMaterial(errorMessage(input.error));
  const message =
    redacted.length > PROVIDER_FAILURE_MESSAGE_MAX_LENGTH
      ? redacted.slice(0, PROVIDER_FAILURE_MESSAGE_MAX_LENGTH)
      : redacted;
  const record: ProviderFailureRecord = {
    provider: input.provider,
    phase: input.phase,
    status: input.status ?? null,
    errorClass: errorClassName(input.error),
    message,
  };
  try {
    const line =
      `[libretiles-provider-failure] ${record.provider} ${record.phase} ` +
      `${String(record.status)} ${record.errorClass} ${record.message}\n`;
    process.stderr.write(line);
  } catch {
    // Logging must never become the primary failure.
  }
  return record;
}
