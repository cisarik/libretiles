import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ApiError human messages", () => {
  it("renders a 429 as a human wait without API error or JSON braces", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          { detail: "Request was throttled. Expected available in 3274 seconds." },
          429,
        ),
      ),
    );
    let caught: unknown;
    try {
      await api.getModels();
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(ApiError);
    const err = caught as ApiError;
    expect(err.status).toBe(429);
    expect(err.message).not.toContain("API error");
    expect(err.message).not.toMatch(/[{}]/);
    expect(err.message).not.toContain("3274 seconds");
    expect(err.message.toLowerCase()).toContain("minute");
  });

  it("surfaces a 400 field-level server message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          { password: ["This password is entirely numeric."] },
          400,
        ),
      ),
    );
    await expect(
      api.register({
        username: "numeric-pass",
        email: "numeric-pass@libretiles.app",
        password: "12345678",
      }),
    ).rejects.toMatchObject({
      status: 400,
      message: "This password is entirely numeric.",
    });
  });

  it("exposes a numeric status so call sites need not substring-match", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "No active account found." }, 401)),
    );
    try {
      await api.login({ username: "nobody", password: "wrong-pass" });
      throw new Error("expected ApiError");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).status).toBe(401);
      expect(typeof (error as ApiError).status).toBe("number");
    }
  });

  it("returns a body with ok: false instead of throwing", async () => {
    // Call site: handleProfilePasswordChange in frontend/src/app/game/[id]/page.tsx
    // (ProfileModal) depends on api.changePassword resolving {ok:false} on HTTP 400.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({ ok: false, error: "Current password is incorrect." }, 400),
      ),
    );
    await expect(
      api.changePassword("synthetic-access", {
        current_password: "old-pass",
        new_password: "new-pass-ok1",
      }),
    ).resolves.toEqual({ ok: false, error: "Current password is incorrect." });
  });
});

describe("api.logout", () => {
  it("posts the refresh token to /api/auth/logout/ with the access token as bearer", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }, 200));
    vi.stubGlobal("fetch", fetchMock);
    await api.logout("synthetic-access-token", "synthetic-refresh-token");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain("/api/auth/logout/");
    expect(init.method).toBe("POST");
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer synthetic-access-token");
    expect(JSON.parse(String(init.body))).toEqual({
      refresh: "synthetic-refresh-token",
    });
  });
});
