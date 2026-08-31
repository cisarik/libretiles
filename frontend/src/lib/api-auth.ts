/**
 * Server-side Django token verification for Next.js AI routes.
 *
 * Django is the JWT authority. This helper never decodes or verifies a token
 * locally. Callers must branch on the returned status; a 401/429 JSON body
 * is never treated as success-shaped input.
 */

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const AUTH_ME_PATH = "/api/auth/me/";
const MAX_RETRY_AFTER_HEADER_LENGTH = 64;

export type TokenVerificationResult =
  | { ok: true }
  | { ok: false; status: 401 | 429 | 503; retryAfter?: string };

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function boundedRetryAfter(value: string | null): string | undefined {
  if (!value) return undefined;
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > MAX_RETRY_AFTER_HEADER_LENGTH) {
    return undefined;
  }
  return trimmed;
}

export function bearerTokenFromAuthorizationHeader(
  header: string | null,
): string | null {
  if (typeof header !== "string") return null;
  const match = /^Bearer (\S+)$/i.exec(header.trim());
  return match ? match[1] : null;
}

export async function verifyUserBearerToken(
  token: string,
): Promise<TokenVerificationResult> {
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}${AUTH_ME_PATH}`, {
      method: "GET",
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    return { ok: false, status: 503 };
  }

  // Branch on HTTP status before reading the body. A 401/429 JSON payload
  // that happens to look like a user profile must not count as authenticated.
  const status = res.status;

  if (status === 401 || status === 403) {
    return { ok: false, status: 401 };
  }

  if (status === 429) {
    const retryAfter = boundedRetryAfter(res.headers.get("Retry-After"));
    return {
      ok: false,
      status: 429,
      ...(retryAfter ? { retryAfter } : {}),
    };
  }

  if (status !== 200) {
    return { ok: false, status: 503 };
  }

  let body: unknown;
  try {
    body = await res.json();
  } catch {
    return { ok: false, status: 503 };
  }

  if (!isObjectRecord(body)) {
    return { ok: false, status: 503 };
  }

  return { ok: true };
}
