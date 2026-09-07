/**
 * Diagnostic-egress policy gate (S7, fake mode only).
 *
 * No policy → deny. The diagnostic seam may only construct a provider runtime
 * and open a socket when BOTH the live sentinel and the explicit egress grant
 * are present. The live egress policy is NOT activated in this slice: every
 * value resolves to deny, so fake runs refuse before any credential lookup,
 * DNS, or socket.
 */

export const DIAGNOSTIC_EGRESS_ENV = "LIBRETILES_DIAGNOSTIC_EGRESS";
const LIVE_SENTINEL_NAME = "LIBRETILES_AI_PLAY_LIVE";

export type DiagnosticEgressMode = "deny" | "live";

export class DiagnosticEgressDeniedError extends Error {
  constructor() {
    super("diagnostic egress policy denied; no live egress grant is active");
    this.name = "DiagnosticEgressDeniedError";
  }
}

export function resolveDiagnosticEgressMode(
  env: NodeJS.ProcessEnv = process.env,
): DiagnosticEgressMode {
  return env[DIAGNOSTIC_EGRESS_ENV] === "live" && env[LIVE_SENTINEL_NAME] === "1"
    ? "live"
    : "deny";
}

/** Must be called BEFORE any credential environment lookup. */
export function assertDiagnosticEgressAllowedBeforeCredential(
  env: NodeJS.ProcessEnv = process.env,
): void {
  if (resolveDiagnosticEgressMode(env) !== "live") {
    throw new DiagnosticEgressDeniedError();
  }
}
