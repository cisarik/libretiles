import fs from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useGameStore } from "@/hooks/useGameStore";
import { LOCALES, type Locale } from "@/lib/i18n/locales";
import { ApiError, api } from "./api";

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function bearerToken(headers: Record<string, string> | undefined): string | null {
  const authorization = headers?.Authorization;
  if (!authorization) return null;
  const match = /^Bearer (.+)$/.exec(authorization);
  return match ? match[1] : null;
}

function noopPersistStorage() {
  return {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  useGameStore.setState(useGameStore.getInitialState(), true);
  useGameStore.persist.setOptions({ storage: noopPersistStorage() });
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

  it("renders a token-bearing 401 as a session expiry, not invalid credentials", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "Given token not valid." }, 401)),
    );
    let caught: unknown;
    try {
      await api.changePassword("synthetic-access", {
        current_password: "old-pass",
        new_password: "new-pass-ok1",
      });
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(ApiError);
    const err = caught as ApiError;
    expect(err.status).toBe(401);
    expect(err.message.toLowerCase()).toContain("session");
    expect(err.message.toLowerCase()).toContain("sign in");
    expect(err.message).not.toContain("Invalid username or password");
    expect(err.message).not.toContain("API error");
    expect(err.message).not.toMatch(/[{}]/);
  });

  it("renders a tokenless 401 as invalid credentials", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "No active account found." }, 401)),
    );
    let caught: unknown;
    try {
      await api.login({ username: "nobody", password: "wrong-pass" });
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(ApiError);
    const err = caught as ApiError;
    expect(err.status).toBe(401);
    expect(err.message).toBe("Invalid username or password");
    expect(err.message).not.toContain("API error");
    expect(err.message).not.toMatch(/[{}]/);
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
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(String(url)).toContain("/api/auth/logout/");
    expect(init.method).toBe("POST");
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer synthetic-access-token");
    expect(JSON.parse(String(init.body))).toEqual({
      refresh: "synthetic-refresh-token",
    });
  });
});

const ENUMERATION_FRAGMENTS = [
  "neexistuje",
  "nenájden",
  "nenalezen",
  "nie istnieje",
  "nie znaleziono",
  "nesprávne heslo",
  "nesprávné heslo",
  "błędne hasło",
  "wrong password",
  "unknown user",
];

// Exact 401 wording is pinned for the four reviewed locales only; the other eight are covered by
// the two SECURITY properties below, which do not need to know what the message says in Icelandic.
// Both loops iterate LOCALES rather than a four-element literal: a literal is what let eight
// locales' 401 strings go unchecked for user-enumeration leakage in the first place.
const LOGIN_401_REVIEWED: Partial<Record<Locale, string>> = {
  en: "Invalid username or password",
  sk: "Nesprávne používateľské meno alebo heslo",
  cs: "Nesprávné uživatelské jméno nebo heslo",
  pl: "Nieprawidłowa nazwa użytkownika lub hasło",
};

const EXPIRED_401_REVIEWED: Partial<Record<Locale, string>> = {
  en: "Your session expired. Please sign in again.",
  sk: "Prihlásenie vypršalo. Prihlás sa znova.",
  cs: "Přihlášení vypršelo. Přihlas se znovu.",
  pl: "Sesja wygasła. Zaloguj się ponownie.",
};

describe("AC-SEC localized 401 messages", () => {
  afterEach(() => {
    useGameStore.setState(useGameStore.getInitialState(), true);
  });

  it("AC-SEC-1: tokenless 401 is identical whether or not the username exists, in every locale", async () => {
    for (const locale of LOCALES) {
      useGameStore.setState({ uiLocale: locale });
      const bodies = [
        { detail: "No active account found." },
        { detail: "Invalid password." },
      ];
      const messages: string[] = [];
      for (const body of bodies) {
        vi.stubGlobal(
          "fetch",
          vi.fn(async () => jsonResponse(body, 401)),
        );
        try {
          await api.login({ username: "nobody", password: "wrong-pass" });
          throw new Error("expected ApiError");
        } catch (error) {
          expect(error).toBeInstanceOf(ApiError);
          messages.push((error as ApiError).message);
        }
      }
      // The security property: both request bodies must produce the SAME string.
      expect(messages[0]).toBe(messages[1]);
      for (const fragment of ENUMERATION_FRAGMENTS) {
        expect(messages[0].toLowerCase()).not.toContain(fragment);
      }
      const pinned = LOGIN_401_REVIEWED[locale];
      if (pinned !== undefined) expect(messages[0]).toBe(pinned);
    }
  });

  it("AC-SEC-2: token-bearing 401 is session-expired wording in every locale", async () => {
    for (const locale of LOCALES) {
      useGameStore.setState({ uiLocale: locale });
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => jsonResponse({ detail: "Given token not valid." }, 401)),
      );
      try {
        await api.changePassword("synthetic-access", {
          current_password: "old-pass",
          new_password: "new-pass-ok1",
        });
        throw new Error("expected ApiError");
      } catch (error) {
        expect(error).toBeInstanceOf(ApiError);
        const err = error as ApiError;
        expect(err.status).toBe(401);
        const pinnedExpired = EXPIRED_401_REVIEWED[locale];
        const pinnedLogin = LOGIN_401_REVIEWED[locale];
        if (pinnedExpired !== undefined) expect(err.message).toBe(pinnedExpired);
        if (pinnedLogin !== undefined) {
          expect(err.message).not.toBe(pinnedLogin);
        }
        // The property, in every locale: an expired session never reuses the login 401 wording,
        // and it never leaks whether the account exists.
        for (const fragment of ENUMERATION_FRAGMENTS) {
          expect(err.message.toLowerCase()).not.toContain(fragment);
        }
      }
    }
  });
});

describe("AC-PLURAL rendered Slovak throttle", () => {
  afterEach(() => {
    useGameStore.setState(useGameStore.getInitialState(), true);
  });

  it("uses minútu/minúty/minút for 1, 2, 4, 5, and 55 minutes", async () => {
    useGameStore.setState({ uiLocale: "sk" });
    const cases: Array<{ seconds: number; suffix: RegExp }> = [
      { seconds: 60, suffix: /minútu\.$/ },
      { seconds: 120, suffix: /2 minúty\.$/ },
      { seconds: 240, suffix: /4 minúty\.$/ },
      { seconds: 300, suffix: /5 minút\.$/ },
      { seconds: 3300, suffix: /55 minút\.$/ },
    ];
    for (const { seconds, suffix } of cases) {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
          jsonResponse(
            { detail: `Request was throttled. Expected available in ${seconds} seconds.` },
            429,
          ),
        ),
      );
      try {
        await api.getModels();
        throw new Error("expected ApiError");
      } catch (error) {
        expect(error).toBeInstanceOf(ApiError);
        expect((error as ApiError).message).toMatch(suffix);
      }
    }
  });
});

describe("api.getVariants", () => {
  it("sends the bearer token to the variants endpoint", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        [
          {
            slug: "english",
            display_name: "English",
            language_code: null,
            readiness: "playable",
          },
        ],
        200,
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const rows = await api.getVariants("synthetic-access");
    expect(rows).toHaveLength(1);
    expect(rows[0]?.slug).toBe("english");
    const firstCall = fetchMock.mock.calls[0];
    expect(firstCall).toBeDefined();
    const [url, init] = firstCall as unknown as [string, RequestInit];
    expect(url).toContain("/api/game/variants/");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer synthetic-access",
    );
  });
});

describe("token refresh session ownership", () => {
  function stubAuthBackend(options: {
    refresh?: (body: string, url: string) => Response | Promise<Response>;
    me?: (token: string | null) => Response | Promise<Response>;
    login?: () => Response | Promise<Response>;
  }) {
    const fetchMock = vi.fn(
      async (url: unknown, init?: RequestInit) => {
        const u = String(url);
        const auth = bearerToken(
          init?.headers as Record<string, string> | undefined,
        );
        if (u.endsWith("/api/auth/refresh/")) {
          if (options.refresh) return options.refresh(String(init?.body ?? ""), u);
          throw new Error(`unexpected refresh ${u}`);
        }
        if (u.endsWith("/api/auth/me/")) {
          if (options.me) return options.me(auth);
          throw new Error(`unexpected me ${u}`);
        }
        if (u.endsWith("/api/auth/login/")) {
          if (options.login) return options.login();
          throw new Error(`unexpected login ${u}`);
        }
        throw new Error(`unexpected URL ${u}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("shares one refresh for overlapping 401s", async () => {
    let releaseRefresh: (() => void) | undefined;
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });
    let refreshCalls = 0;
    const meCalls: string[] = [];
    const fetchMock = stubAuthBackend({
      refresh: async () => {
        refreshCalls += 1;
        await refreshGate;
        return jsonResponse({ access: "new-access", refresh: "new-refresh" }, 200);
      },
      me: (token) => {
        meCalls.push(token ?? "");
        if (token === "new-access") return jsonResponse({ username: "alice" }, 200);
        return jsonResponse({ detail: "expired" }, 401);
      },
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    const first = api.me("access-1");
    const second = api.me("access-1");
    await vi.waitFor(() => {
      expect(refreshCalls).toBe(1);
      expect(meCalls.filter((token) => token === "access-1")).toHaveLength(2);
    });
    releaseRefresh?.();
    expect(await first).toEqual({ username: "alice" });
    expect(await second).toEqual({ username: "alice" });
    expect(refreshCalls).toBe(1);
    expect(meCalls.filter((token) => token === "new-access")).toHaveLength(2);
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/api/auth/refresh/"),
      ),
    ).toHaveLength(1);
  });

  it("reuses the rotated access token for a late stale 401", async () => {
    let releaseLate: (() => void) | undefined;
    const lateGate = new Promise<void>((resolve) => {
      releaseLate = resolve;
    });
    let access1Calls = 0;
    let refreshCalls = 0;
    const meCalls: string[] = [];
    stubAuthBackend({
      refresh: () => {
        refreshCalls += 1;
        return jsonResponse({ access: "access-2" }, 200);
      },
      me: async (token) => {
        meCalls.push(token ?? "");
        if (token === "access-1") {
          access1Calls += 1;
          if (access1Calls === 1) await lateGate;
          return jsonResponse({ detail: "expired" }, 401);
        }
        if (token === "access-2") return jsonResponse({ username: "alice" }, 200);
        return jsonResponse({ detail: "expired" }, 401);
      },
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    const slow = api.me("access-1");
    const quick = api.me("access-1");
    expect(await quick).toEqual({ username: "alice" });
    releaseLate?.();
    expect(await slow).toEqual({ username: "alice" });
    expect(refreshCalls).toBe(1);
    expect(meCalls.filter((token) => token === "access-2")).toHaveLength(2);
  });

  it("does not refresh tokenless requests or 403s", async () => {
    const fetchMock = stubAuthBackend({
      login: () => jsonResponse({ detail: "No active account found." }, 401),
      me: () => jsonResponse({ detail: "Forbidden." }, 403),
    });
    await expect(
      api.login({ username: "nobody", password: "wrong-pass" }),
    ).rejects.toBeInstanceOf(ApiError);
    await expect(api.me("access-1")).rejects.toBeInstanceOf(ApiError);
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/api/auth/refresh/"),
      ),
    ).toHaveLength(0);
  });

  it("retries each request at most once", async () => {
    let refreshCalls = 0;
    const fetchMock = stubAuthBackend({
      refresh: () => {
        refreshCalls += 1;
        return jsonResponse({ access: "new-access" }, 200);
      },
      me: (token) => {
        if (token === "new-access") return jsonResponse({ detail: "expired" }, 401);
        return jsonResponse({ detail: "expired" }, 401);
      },
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    await expect(api.me("access-1")).rejects.toMatchObject({ status: 401 });
    expect(refreshCalls).toBe(1);
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/api/auth/me/"),
      ),
    ).toHaveLength(2);
  });

  it("clears only its own auth on a rejected refresh", async () => {
    stubAuthBackend({
      refresh: () => jsonResponse({ detail: "Token is invalid or expired." }, 401),
      me: () => jsonResponse({ detail: "expired" }, 401),
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    await expect(api.me("access-1")).rejects.toMatchObject({ status: 401 });
    const state = useGameStore.getState();
    expect(state.token).toBeNull();
    expect(state.refreshToken).toBeNull();
  });

  it("rejects malformed refresh payloads without applying them", async () => {
    const payloads: unknown[] = [
      {},
      { access: 5 },
      { access: "" },
      { access: "x", refresh: 5 },
      { access: "x", refresh: "" },
    ];
    for (const payload of payloads) {
      useGameStore.setState(useGameStore.getInitialState(), true);
      const fetchMock = stubAuthBackend({
        refresh: () => jsonResponse(payload, 200),
        me: () => jsonResponse({ detail: "expired" }, 401),
      });
      useGameStore.getState().setToken("access-1");
      useGameStore.getState().setRefreshToken("refresh-1");
      await expect(api.me("access-1")).rejects.toMatchObject({ status: 401 });
      expect(useGameStore.getState().token).toBeNull();
      expect(
        fetchMock.mock.calls.filter(([url]) =>
          String(url).endsWith("/api/auth/me/"),
        ),
      ).toHaveLength(1);
      vi.unstubAllGlobals();
    }
  });

  it("preserves auth on a refresh transport failure", async () => {
    stubAuthBackend({
      refresh: () => {
        throw new Error("network down");
      },
      me: () => jsonResponse({ detail: "expired" }, 401),
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    await expect(api.me("access-1")).rejects.toMatchObject({ status: 401 });
    const state = useGameStore.getState();
    expect(state.token).toBe("access-1");
    expect(state.refreshToken).toBe("refresh-1");
  });

  it("ignores a refresh success that lands after logout", async () => {
    let releaseRefresh: (() => void) | undefined;
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });
    const fetchMock = stubAuthBackend({
      refresh: async () => {
        await refreshGate;
        return jsonResponse({ access: "new-access" }, 200);
      },
      me: () => jsonResponse({ detail: "expired" }, 401),
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    const pending = api.me("access-1");
    await vi.waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).endsWith("/api/auth/refresh/"),
        ),
      ).toBe(true);
    });
    useGameStore.getState().clearAuth();
    releaseRefresh?.();
    await expect(pending).rejects.toMatchObject({ status: 401 });
    const state = useGameStore.getState();
    expect(state.token).toBeNull();
    expect(state.refreshToken).toBeNull();
  });

  it("ignores a refresh success that lands after an account switch", async () => {
    let releaseRefresh: (() => void) | undefined;
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });
    const fetchMock = stubAuthBackend({
      refresh: async () => {
        await refreshGate;
        return jsonResponse({ access: "new-access" }, 200);
      },
      me: () => jsonResponse({ detail: "expired" }, 401),
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    const pending = api.me("access-1");
    await vi.waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).endsWith("/api/auth/refresh/"),
        ),
      ).toBe(true);
    });
    useGameStore.getState().setToken("access-2");
    useGameStore.getState().setRefreshToken("refresh-2");
    releaseRefresh?.();
    await expect(pending).rejects.toMatchObject({ status: 401 });
    const state = useGameStore.getState();
    expect(state.token).toBe("access-2");
    expect(state.refreshToken).toBe("refresh-2");
  });

  it("does not clear a new account when an old refresh fails", async () => {
    let releaseRefresh: (() => void) | undefined;
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });
    const fetchMock = stubAuthBackend({
      refresh: async () => {
        await refreshGate;
        return jsonResponse({ detail: "Token is invalid or expired." }, 401);
      },
      me: () => jsonResponse({ detail: "expired" }, 401),
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    const pending = api.me("access-1");
    await vi.waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).endsWith("/api/auth/refresh/"),
        ),
      ).toBe(true);
    });
    useGameStore.getState().setToken("access-2");
    useGameStore.getState().setRefreshToken("refresh-2");
    releaseRefresh?.();
    await expect(pending).rejects.toMatchObject({ status: 401 });
    const state = useGameStore.getState();
    expect(state.token).toBe("access-2");
    expect(state.refreshToken).toBe("refresh-2");
  });

  it("never joins an old refresh flight from a different account", async () => {
    let releaseRefresh: (() => void) | undefined;
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });
    const refreshBodies: string[] = [];
    const fetchMock = stubAuthBackend({
      refresh: async (body) => {
        refreshBodies.push(body);
        await refreshGate;
        return jsonResponse({ access: "new-access" }, 200);
      },
      me: (token) => {
        if (token === "new-access") return jsonResponse({ username: "alice" }, 200);
        return jsonResponse({ detail: "expired" }, 401);
      },
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    const old = api.me("access-1").catch(() => null);
    await vi.waitFor(() => expect(refreshBodies).toHaveLength(1));
    useGameStore.getState().setToken("access-2");
    useGameStore.getState().setRefreshToken("refresh-2");
    const fresh = api.me("access-2");
    await vi.waitFor(() => expect(refreshBodies).toHaveLength(2));
    expect(refreshBodies[0]).toContain("refresh-1");
    expect(refreshBodies[1]).toContain("refresh-2");
    releaseRefresh?.();
    await old;
    expect(await fresh).toEqual({ username: "alice" });
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/api/auth/refresh/"),
      ),
    ).toHaveLength(2);
  });

  it("old flight cleanup never clears a newer flight", async () => {
    let releaseOld: (() => void) | undefined;
    let releaseNew: (() => void) | undefined;
    const oldGate = new Promise<void>((resolve) => {
      releaseOld = resolve;
    });
    const newGate = new Promise<void>((resolve) => {
      releaseNew = resolve;
    });
    let refreshCalls = 0;
    const meCalls: string[] = [];
    stubAuthBackend({
      refresh: async () => {
        refreshCalls += 1;
        if (refreshCalls === 1) {
          await oldGate;
        } else {
          await newGate;
        }
        return jsonResponse({ detail: "Token is invalid or expired." }, 401);
      },
      me: (token) => {
        meCalls.push(token ?? "");
        return jsonResponse({ detail: "expired" }, 401);
      },
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    const old = api.me("access-1").catch(() => null);
    await vi.waitFor(() => expect(refreshCalls).toBe(1));
    useGameStore.getState().setToken("access-2");
    useGameStore.getState().setRefreshToken("refresh-2");
    const newRequest = api.me("access-2").catch(() => null);
    await vi.waitFor(() => expect(refreshCalls).toBe(2));
    releaseOld?.();
    await old;
    // A 401 for the new account after the old flight finished must share the
    // still-pending new flight; if the old cleanup had cleared the slot, a
    // third refresh would start here.
    const late = api.me("access-2").catch(() => null);
    await vi.waitFor(() =>
      expect(meCalls.filter((token) => token === "access-2")).toHaveLength(2),
    );
    expect(refreshCalls).toBe(2);
    releaseNew?.();
    await newRequest;
    await late;
    expect(refreshCalls).toBe(2);
  });

  it("does not refresh an explicit token from another session", async () => {
    const fetchMock = stubAuthBackend({
      me: () => jsonResponse({ detail: "expired" }, 401),
    });
    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    await expect(api.me("other-session-token")).rejects.toMatchObject({
      status: 401,
    });
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/api/auth/refresh/"),
      ),
    ).toHaveLength(0);
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/api/auth/me/"),
      ),
    ).toHaveLength(1);
    expect(useGameStore.getState().token).toBe("access-1");
  });

  it("keeps authEpoch transient and bumps only on login, logout, and hydration", async () => {
    const initialState = useGameStore.getState();
    expect(initialState.authEpoch).toBe(0);
    const partialize = useGameStore.persist.getOptions().partialize as
      | ((state: unknown) => Record<string, unknown>)
      | undefined;
    expect(partialize).toBeDefined();
    const persistedSnapshot = partialize!(useGameStore.getState());
    expect(persistedSnapshot).not.toHaveProperty("authEpoch");
    expect(persistedSnapshot).toHaveProperty("token");
    expect(persistedSnapshot).toHaveProperty("refreshToken");

    useGameStore.getState().setToken("access-1");
    useGameStore.getState().setRefreshToken("refresh-1");
    expect(useGameStore.getState().authEpoch).toBe(2);

    const fetchMock = stubAuthBackend({
      refresh: () =>
        jsonResponse({ access: "access-2", refresh: "refresh-2" }, 200),
      me: (token) => {
        if (token === "access-2") return jsonResponse({ username: "alice" }, 200);
        return jsonResponse({ detail: "expired" }, 401);
      },
    });
    expect(await api.me("access-1")).toEqual({ username: "alice" });
    const afterRefresh = useGameStore.getState();
    expect(afterRefresh.authEpoch).toBe(2);
    expect(afterRefresh.token).toBe("access-2");
    expect(afterRefresh.refreshToken).toBe("refresh-2");
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/api/auth/refresh/"),
      ),
    ).toHaveLength(1);

    afterRefresh.clearAuth();
    expect(useGameStore.getState().authEpoch).toBe(3);

    // Hydrating a persisted token pair belongs to a previous runtime: the
    // epoch bumps, so in-flight work captured before hydration cannot commit.
    vi.unstubAllGlobals();
    useGameStore.persist.setOptions({
      storage: {
        getItem: () => ({
          state: { token: "persisted-access", refreshToken: "persisted-refresh" },
          version: 6,
        }),
        setItem: () => {},
        removeItem: () => {},
      },
    });
    await useGameStore.persist.rehydrate();
    const hydrated = useGameStore.getState();
    expect(hydrated.token).toBe("persisted-access");
    expect(hydrated.refreshToken).toBe("persisted-refresh");
    expect(hydrated.authEpoch).toBeGreaterThan(3);
    expect(
      hydrated.applyRefreshedAuth(
        {
          epoch: 3,
          token: "persisted-access",
          refreshToken: "persisted-refresh",
        },
        { access: "new-access" },
      ),
    ).toBe(false);
    expect(useGameStore.getState().token).toBe("persisted-access");
  });
});

describe("NEXT_PUBLIC_ surface", () => {
  it("keeps NEXT_PUBLIC_API_URL the only NEXT_PUBLIC_ identifier under src", () => {
    const root = path.join(__dirname, "..");
    const found = new Set<string>();
    const walk = (dir: string): void => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name === ".next" || entry.name === "node_modules") continue;
          walk(full);
        } else if (entry.isFile()) {
          const text = fs.readFileSync(full, "utf8");
          for (const match of text.matchAll(/NEXT_PUBLIC_[A-Z0-9_]+/g)) {
            found.add(match[0]);
          }
        }
      }
    };
    walk(root);
    expect([...found].sort()).toEqual(["NEXT_PUBLIC_API_URL"]);
  });
});
