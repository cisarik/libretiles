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
// Space, colon, underscore, or hyphen after Bearer (hyphen-joined tokens
// such as the watsonx sanitisation fixture were missed by `\s+` alone).
const BEARER_PATTERN = /Bearer[\s:_-]+\S+/gi;
// Defence-in-depth floor below the previous 24-character threshold so a
// 16-character credential-shaped run is still caught when value matching
// cannot see it.
const HIGH_ENTROPY_RUN = /[A-Za-z0-9+/=_\-]{16,}/g;

const CREDENTIAL_ENV_NAMES = [
  "GROQ_API_KEY",
  "GEMINI_API_KEY",
  "MISTRAL_API_KEY",
  "AION_API_KEY",
  "HF_TOKEN",
  "CLOUDFLARE_ACCOUNT_ID",
  "CLOUDFLARE_API_TOKEN",
  "OPENROUTER_API_KEY",
  "NVIDIA_API_KEY",
  "IBM_CLOUD_API_KEY",
  "IBM_WATSONX_PROJECT_ID",
  "IBM_WATSONX_REGION",
] as const;

// Values shorter than this are skipped: a 3-character replace would blank
// ordinary diagnostic words. Eight characters is above common English
// fragments ("error", "HTTP") while still covering the project's own
// 16- and 17-character watsonx fixtures. Region codes such as `eu-de`
// fall below this floor and are covered by omitting the raw
// `provider_transport` message rather than by value matching.
const MIN_CREDENTIAL_VALUE_LENGTH = 8;

const TRANSPORT_FAILURE_MESSAGE = "transport failure";

function entropyRatio(value: string): number {
  if (!value) return 0;
  return new Set(value).size / value.length;
}

function isPlaceholderCredential(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return (
    normalized.startsWith("your-") ||
    normalized.includes("placeholder") ||
    normalized.includes("replace-me") ||
    normalized === "changeme" ||
    normalized === "change-me"
  );
}

function replaceLiteralAll(
  haystack: string,
  needle: string,
  replacement: string,
): string {
  if (!needle) return haystack;
  let out = haystack;
  let index = out.indexOf(needle);
  while (index !== -1) {
    out = out.slice(0, index) + replacement + out.slice(index + needle.length);
    index = out.indexOf(needle, index + replacement.length);
  }
  return out;
}

function heldCredentialValues(): string[] {
  const held: string[] = [];
  for (const name of CREDENTIAL_ENV_NAMES) {
    const raw = process.env[name];
    if (typeof raw !== "string") continue;
    const trimmed = raw.trim();
    if (!trimmed) continue;
    if (isPlaceholderCredential(trimmed)) continue;
    if (trimmed.length < MIN_CREDENTIAL_VALUE_LENGTH) continue;
    held.push(trimmed);
  }
  held.sort((a, b) => b.length - a.length);
  return held;
}

function redactCredentialMaterial(message: string): string {
  let out = message;
  for (const value of heldCredentialValues()) {
    out = replaceLiteralAll(out, value, "[redacted]");
  }
  out = out.replace(BEARER_PATTERN, "Bearer [redacted]");
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
  // Fetch-layer failures are the highest-risk phase: the watsonx IAM
  // request body carries the API key, and a provider error can echo it.
  // Error class and status remain; the raw message does not.
  const diagnostic =
    input.phase === "provider_transport" ? TRANSPORT_FAILURE_MESSAGE : redacted;
  const message =
    diagnostic.length > PROVIDER_FAILURE_MESSAGE_MAX_LENGTH
      ? diagnostic.slice(0, PROVIDER_FAILURE_MESSAGE_MAX_LENGTH)
      : diagnostic;
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
