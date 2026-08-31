import { afterEach, describe, expect, it, vi } from "vitest";
import {
  bearerTokenFromAuthorizationHeader,
  verifyUserBearerToken,
} from "./api-auth";

const SYNTHETIC_TOKEN = "test-judge-token";
const PROFILE = {
  id: 1,
  username: "judge-user",
  email: "judge-user@example.test",
  preferred_ai_model_id: "",
  date_joined: "2026-01-01T00:00:00Z",
};

function jsonResponse(
  value: unknown,
  status: number,
  headers?: Record<string, string>,
): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("bearerTokenFromAuthorizationHeader", () => {
  it("returns null when the header is missing or not Bearer", () => {
    expect(bearerTokenFromAuthorizationHeader(null)).toBeNull();
    expect(bearerTokenFromAuthorizationHeader("")).toBeNull();
    expect(bearerTokenFromAuthorizationHeader("Token abc")).toBeNull();
    expect(bearerTokenFromAuthorizationHeader("Bearer")).toBeNull();
    expect(bearerTokenFromAuthorizationHeader("Bearer ")).toBeNull();
    expect(bearerTokenFromAuthorizationHeader("Bearer a b")).toBeNull();
  });

  it("returns the token from a Bearer header", () => {
    expect(bearerTokenFromAuthorizationHeader(`Bearer ${SYNTHETIC_TOKEN}`)).toBe(
      SYNTHETIC_TOKEN,
    );
    expect(
      bearerTokenFromAuthorizationHeader(`bearer ${SYNTHETIC_TOKEN}`),
    ).toBe(SYNTHETIC_TOKEN);
  });
});

describe("verifyUserBearerToken", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("succeeds only on HTTP 200 with a JSON object body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(PROFILE, 200)),
    );
    await expect(verifyUserBearerToken(SYNTHETIC_TOKEN)).resolves.toEqual({
      ok: true,
    });
  });

  it("maps Django 401 and 403 to 401 without treating the body as success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(PROFILE, 401)),
    );
    await expect(verifyUserBearerToken(SYNTHETIC_TOKEN)).resolves.toEqual({
      ok: false,
      status: 401,
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(PROFILE, 403)),
    );
    await expect(verifyUserBearerToken(SYNTHETIC_TOKEN)).resolves.toEqual({
      ok: false,
      status: 401,
    });
  });

  it("propagates HTTP 429 from status, not from a success-shaped body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(PROFILE, 429, { "Retry-After": "12" })),
    );
    await expect(verifyUserBearerToken(SYNTHETIC_TOKEN)).resolves.toEqual({
      ok: false,
      status: 429,
      retryAfter: "12",
    });
  });

  it("fails closed with 503 on network rejection, non-JSON, or unexpected body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("backend unreachable");
      }),
    );
    await expect(verifyUserBearerToken(SYNTHETIC_TOKEN)).resolves.toEqual({
      ok: false,
      status: 503,
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>nope</html>", { status: 200 })),
    );
    await expect(verifyUserBearerToken(SYNTHETIC_TOKEN)).resolves.toEqual({
      ok: false,
      status: 503,
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse([{ provider: "openrouter" }], 200)),
    );
    await expect(verifyUserBearerToken(SYNTHETIC_TOKEN)).resolves.toEqual({
      ok: false,
      status: 503,
    });

    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(PROFILE, 500)));
    await expect(verifyUserBearerToken(SYNTHETIC_TOKEN)).resolves.toEqual({
      ok: false,
      status: 503,
    });
  });
});
