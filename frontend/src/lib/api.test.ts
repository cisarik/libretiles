import { afterEach, describe, expect, it, vi } from "vitest";
import { useGameStore } from "@/hooks/useGameStore";
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

describe("AC-SEC localized 401 messages", () => {
  afterEach(() => {
    useGameStore.setState(useGameStore.getInitialState(), true);
  });

  it("AC-SEC-1: tokenless 401 is identical whether or not the username exists, in all four locales", async () => {
    const loginByLocale = {
      en: "Invalid username or password",
      sk: "Nesprávne používateľské meno alebo heslo",
      cs: "Nesprávné uživatelské jméno nebo heslo",
      pl: "Nieprawidłowa nazwa użytkownika lub hasło",
    } as const;
    for (const locale of ["en", "sk", "cs", "pl"] as const) {
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
      expect(messages[0]).toBe(messages[1]);
      expect(messages[0]).toBe(loginByLocale[locale]);
      for (const fragment of ENUMERATION_FRAGMENTS) {
        expect(messages[0].toLowerCase()).not.toContain(fragment);
      }
    }
  });

  it("AC-SEC-2: token-bearing 401 is session-expired wording in all four locales", async () => {
    const loginByLocale = {
      en: "Invalid username or password",
      sk: "Nesprávne používateľské meno alebo heslo",
      cs: "Nesprávné uživatelské jméno nebo heslo",
      pl: "Nieprawidłowa nazwa użytkownika lub hasło",
    } as const;
    const expiredByLocale = {
      en: "Your session expired. Please sign in again.",
      sk: "Prihlásenie vypršalo. Prihlás sa znova.",
      cs: "Přihlášení vypršelo. Přihlas se znovu.",
      pl: "Sesja wygasła. Zaloguj się ponownie.",
    } as const;
    for (const locale of ["en", "sk", "cs", "pl"] as const) {
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
        expect(err.message).toBe(expiredByLocale[locale]);
        expect(err.message).not.toBe(loginByLocale[locale]);
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
