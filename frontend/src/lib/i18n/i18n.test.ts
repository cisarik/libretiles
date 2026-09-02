import { describe, expect, it } from "vitest";
import { t, tf } from "./index";
import {
  detectBrowserLocale,
  isLocale,
  localeSyncDecision,
  LOCALES,
} from "./locales";
import { csFn, csText } from "./messages.cs";
import { enFn, enText } from "./messages.en";
import { plFn, plText } from "./messages.pl";
import { skFn, skText } from "./messages.sk";
import { pluralCs, pluralPl, pluralSk } from "./plural";

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

describe("AC-DETECT4 detectBrowserLocale", () => {
  it("maps sk/cs/pl primary subtags case-insensitively and rejects cz", () => {
    expect(detectBrowserLocale(["sk"])).toBe("sk");
    expect(detectBrowserLocale(["sk-SK"])).toBe("sk");
    expect(detectBrowserLocale(["SK"])).toBe("sk");
    expect(detectBrowserLocale(["sk-SK", "en"])).toBe("sk");
    expect(detectBrowserLocale(["cs"])).toBe("cs");
    expect(detectBrowserLocale(["cs-CZ"])).toBe("cs");
    expect(detectBrowserLocale(["CS"])).toBe("cs");
    expect(detectBrowserLocale(["pl"])).toBe("pl");
    expect(detectBrowserLocale(["pl-PL"])).toBe("pl");
    expect(detectBrowserLocale(["en-US"])).toBe("en");
    expect(detectBrowserLocale(["cz-CZ"])).toBe("en");
    expect(detectBrowserLocale(["sks"])).toBe("en");
    expect(detectBrowserLocale(["hu"])).toBe("en");
    expect(detectBrowserLocale([])).toBe("en");
  });
});

describe("AC-ISLOCALE", () => {
  it("accepts exactly the four locales and rejects other values", () => {
    expect(isLocale("en")).toBe(true);
    expect(isLocale("sk")).toBe(true);
    expect(isLocale("cs")).toBe(true);
    expect(isLocale("pl")).toBe(true);
    expect(isLocale("")).toBe(false);
    expect(isLocale("fr")).toBe(false);
    expect(isLocale("hu")).toBe(false);
    expect(isLocale("cz")).toBe(false);
    expect(isLocale("EN")).toBe(false);
    expect(isLocale(null)).toBe(false);
    expect(isLocale(undefined)).toBe(false);
    expect(isLocale(0)).toBe(false);
    expect(isLocale({})).toBe(false);
  });
});

describe("AC-SYNC localeSyncDecision", () => {
  it("AC-SYNC-1: identical server and resolved locales do not write or refresh", () => {
    for (const locale of LOCALES) {
      expect(localeSyncDecision(locale, locale)).toEqual({
        cookie: null,
        refresh: false,
      });
    }
  });

  it("AC-SYNC-2: a mismatch writes the resolved locale and requests refresh", () => {
    expect(localeSyncDecision("en", "sk")).toEqual({
      cookie: "sk",
      refresh: true,
    });
    expect(localeSyncDecision("sk", "cs")).toEqual({
      cookie: "cs",
      refresh: true,
    });
    expect(localeSyncDecision("cs", "pl")).toEqual({
      cookie: "pl",
      refresh: true,
    });
    expect(localeSyncDecision("pl", "en")).toEqual({
      cookie: "en",
      refresh: true,
    });
  });

  it("AC-SYNC-3: feeding the written cookie back as the next server locale terminates", () => {
    for (const server of LOCALES) {
      for (const resolved of LOCALES) {
        if (server === resolved) continue;
        const first = localeSyncDecision(server, resolved);
        expect(first).toEqual({ cookie: resolved, refresh: true });
        const second = localeSyncDecision(first.cookie!, resolved);
        expect(second).toEqual({ cookie: null, refresh: false });
      }
    }
  });
});

describe("AC-EXHAUST catalogs share one key set", () => {
  it("matches en/sk/cs/pl text and function keys at runtime", () => {
    const textKeys = Object.keys(enText).sort();
    expect(Object.keys(skText).sort()).toEqual(textKeys);
    expect(Object.keys(csText).sort()).toEqual(textKeys);
    expect(Object.keys(plText).sort()).toEqual(textKeys);
    const fnKeys = Object.keys(enFn).sort();
    expect(Object.keys(skFn).sort()).toEqual(fnKeys);
    expect(Object.keys(csFn).sort()).toEqual(fnKeys);
    expect(Object.keys(plFn).sort()).toEqual(fnKeys);
  });
});

describe("AC-PLURAL Slovak three-form helper", () => {
  it("returns one/few/many for the named counts and negatives", () => {
    expect(pluralSk(0, "one", "few", "many")).toBe("many");
    expect(pluralSk(1, "one", "few", "many")).toBe("one");
    expect(pluralSk(2, "one", "few", "many")).toBe("few");
    expect(pluralSk(4, "one", "few", "many")).toBe("few");
    expect(pluralSk(5, "one", "few", "many")).toBe("many");
    expect(pluralSk(11, "one", "few", "many")).toBe("many");
    expect(pluralSk(21, "one", "few", "many")).toBe("many");
    expect(pluralSk(101, "one", "few", "many")).toBe("many");
    expect(pluralSk(-1, "one", "few", "many")).toBe("one");
    expect(pluralSk(-2, "one", "few", "many")).toBe("few");
    expect(pluralSk(-5, "one", "few", "many")).toBe("many");
  });

  it("renders Slovak throttle minutes through the parameterised message", () => {
    const minuteWord = (minutes: number) =>
      tf("sk", "error.throttled.minutes", { minutes });

    expect(minuteWord(1)).toMatch(/1 minútu\.$/);
    expect(minuteWord(2)).toMatch(/2 minúty\.$/);
    expect(minuteWord(4)).toMatch(/4 minúty\.$/);
    expect(minuteWord(5)).toMatch(/5 minút\.$/);
    expect(minuteWord(55)).toMatch(/55 minút\.$/);
  });
});

describe("AC-PLURAL-PL Polish last-digit helper", () => {
  it("returns one/few/many for the named counts and negatives", () => {
    expect(pluralPl(0, "one", "few", "many")).toBe("many");
    expect(pluralPl(1, "one", "few", "many")).toBe("one");
    expect(pluralPl(2, "one", "few", "many")).toBe("few");
    expect(pluralPl(4, "one", "few", "many")).toBe("few");
    expect(pluralPl(5, "one", "few", "many")).toBe("many");
    expect(pluralPl(11, "one", "few", "many")).toBe("many");
    expect(pluralPl(12, "one", "few", "many")).toBe("many");
    expect(pluralPl(13, "one", "few", "many")).toBe("many");
    expect(pluralPl(14, "one", "few", "many")).toBe("many");
    expect(pluralPl(21, "one", "few", "many")).toBe("many");
    expect(pluralPl(22, "one", "few", "many")).toBe("few");
    expect(pluralPl(23, "one", "few", "many")).toBe("few");
    expect(pluralPl(24, "one", "few", "many")).toBe("few");
    expect(pluralPl(25, "one", "few", "many")).toBe("many");
    expect(pluralPl(101, "one", "few", "many")).toBe("many");
    expect(pluralPl(111, "one", "few", "many")).toBe("many");
    expect(pluralPl(112, "one", "few", "many")).toBe("many");
    expect(pluralPl(122, "one", "few", "many")).toBe("few");
    expect(pluralPl(-1, "one", "few", "many")).toBe("one");
    expect(pluralPl(-2, "one", "few", "many")).toBe("few");
    expect(pluralPl(-5, "one", "few", "many")).toBe("many");
    expect(pluralPl(-22, "one", "few", "many")).toBe("few");
  });

  it("differs from pluralSk at 22, 23, 24, 122, 123, and 124", () => {
    for (const n of [22, 23, 24, 122, 123, 124]) {
      expect(pluralPl(n, "one", "few", "many")).toBe("few");
      expect(pluralSk(n, "one", "few", "many")).toBe("many");
    }
  });
});

describe("AC-PLURAL-CS Czech shares the Slovak integer rule", () => {
  it("agrees with pluralSk on the same inputs", () => {
    for (const n of [0, 1, 2, 4, 5, 11, 12, 13, 14, 21, 22, 23, 24, 25, 101, 111, 112, 122, -1, -2, -5]) {
      expect(pluralCs(n, "one", "few", "many")).toBe(
        pluralSk(n, "one", "few", "many"),
      );
    }
  });

  it("renders Czech throttle minutes as minutu/minuty/minut", () => {
    const minuteWord = (minutes: number) =>
      tf("cs", "error.throttled.minutes", { minutes });

    expect(minuteWord(1)).toMatch(/1 minutu\.$/);
    expect(minuteWord(2)).toMatch(/2 minuty\.$/);
    expect(minuteWord(4)).toMatch(/4 minuty\.$/);
    expect(minuteWord(5)).toMatch(/5 minut\.$/);
    expect(minuteWord(55)).toMatch(/55 minut\.$/);
  });
});

describe("AC-PLURAL-PL2 Polish throttle message", () => {
  it("renders minutę/minuty/minut including the n=22 few form", () => {
    const minuteWord = (minutes: number) =>
      tf("pl", "error.throttled.minutes", { minutes });

    expect(minuteWord(1)).toMatch(/1 minutę\.$/);
    expect(minuteWord(2)).toMatch(/2 minuty\.$/);
    expect(minuteWord(4)).toMatch(/4 minuty\.$/);
    expect(minuteWord(5)).toMatch(/5 minut\.$/);
    expect(minuteWord(22)).toMatch(/22 minuty\.$/);
    expect(minuteWord(55)).toMatch(/55 minut\.$/);
  });
});

describe("AC-SEC message catalogs", () => {
  it("keeps login 401 free of user-enumeration fragments in all four locales", () => {
    const loginByLocale = {
      en: enText["error.invalidCredentials"],
      sk: skText["error.invalidCredentials"],
      cs: csText["error.invalidCredentials"],
      pl: plText["error.invalidCredentials"],
    } as const;
    expect(loginByLocale.en).toBe("Invalid username or password");
    expect(loginByLocale.sk).toBe("Nesprávne používateľské meno alebo heslo");
    expect(loginByLocale.cs).toBe("Nesprávné uživatelské jméno nebo heslo");
    expect(loginByLocale.pl).toBe("Nieprawidłowa nazwa użytkownika lub hasło");
    for (const login of Object.values(loginByLocale)) {
      const lower = login.toLowerCase();
      for (const fragment of ENUMERATION_FRAGMENTS) {
        expect(lower).not.toContain(fragment);
      }
    }
  });

  it("keeps session-expired wording distinct from login 401 in all four locales", () => {
    expect(enText["error.sessionExpired"]).toBe(
      "Your session expired. Please sign in again.",
    );
    expect(skText["error.sessionExpired"]).toBe(
      "Prihlásenie vypršalo. Prihlás sa znova.",
    );
    expect(csText["error.sessionExpired"]).toBe(
      "Přihlášení vypršelo. Přihlas se znovu.",
    );
    expect(plText["error.sessionExpired"]).toBe(
      "Sesja wygasła. Zaloguj się ponownie.",
    );
    expect(enText["error.sessionExpired"]).not.toBe(
      enText["error.invalidCredentials"],
    );
    expect(skText["error.sessionExpired"]).not.toBe(
      skText["error.invalidCredentials"],
    );
    expect(csText["error.sessionExpired"]).not.toBe(
      csText["error.invalidCredentials"],
    );
    expect(plText["error.sessionExpired"]).not.toBe(
      plText["error.invalidCredentials"],
    );
  });
});

describe("AC-TILES-4 controls.tilesSelected counted tile noun", () => {
  const COUNTS = [0, 1, 2, 4, 5, 22, 25] as const;

  it("renders English with a literal s suffix", () => {
    const expected: Record<(typeof COUNTS)[number], string> = {
      0: "0 tiles selected",
      1: "1 tile selected",
      2: "2 tiles selected",
      4: "4 tiles selected",
      5: "5 tiles selected",
      22: "22 tiles selected",
      25: "25 tiles selected",
    };
    for (const count of COUNTS) {
      expect(tf("en", "controls.tilesSelected", { count })).toBe(expected[count]);
    }
  });

  it("renders Slovak colon-label plus pluralSk tile noun", () => {
    const expected: Record<(typeof COUNTS)[number], string> = {
      0: "Výber: 0 písmen",
      1: "Výber: 1 písmeno",
      2: "Výber: 2 písmená",
      4: "Výber: 4 písmená",
      5: "Výber: 5 písmen",
      22: "Výber: 22 písmen",
      25: "Výber: 25 písmen",
    };
    for (const count of COUNTS) {
      expect(tf("sk", "controls.tilesSelected", { count })).toBe(expected[count]);
    }
  });

  it("renders Czech colon-label plus pluralCs kámen forms", () => {
    const expected: Record<(typeof COUNTS)[number], string> = {
      0: "Výběr: 0 kamenů",
      1: "Výběr: 1 kámen",
      2: "Výběr: 2 kameny",
      4: "Výběr: 4 kameny",
      5: "Výběr: 5 kamenů",
      22: "Výběr: 22 kamenů",
      25: "Výběr: 25 kamenů",
    };
    for (const count of COUNTS) {
      expect(tf("cs", "controls.tilesSelected", { count })).toBe(expected[count]);
    }
  });

  it("renders Polish colon-label plus pluralPl płytka forms", () => {
    const expected: Record<(typeof COUNTS)[number], string> = {
      0: "Wybrane: 0 płytek",
      1: "Wybrane: 1 płytka",
      2: "Wybrane: 2 płytki",
      4: "Wybrane: 4 płytki",
      5: "Wybrane: 5 płytek",
      22: "Wybrane: 22 płytki",
      25: "Wybrane: 25 płytek",
    };
    for (const count of COUNTS) {
      expect(tf("pl", "controls.tilesSelected", { count })).toBe(expected[count]);
    }
  });
});

describe("AC-TILES-PL22 Polish 22 uses few, not Slovak many", () => {
  it("diverges from pluralSk at count 22 in the same assertion", () => {
    const sk22 = tf("sk", "controls.tilesSelected", { count: 22 });
    const cs22 = tf("cs", "controls.tilesSelected", { count: 22 });
    const pl22 = tf("pl", "controls.tilesSelected", { count: 22 });
    expect(sk22).toBe("Výber: 22 písmen");
    expect(cs22).toBe("Výběr: 22 kamenů");
    expect(pl22).toBe("Wybrane: 22 płytki");
    const pluralSkWouldHaveProduced = `Wybrane: 22 ${pluralSk(22, "płytka", "płytki", "płytek")}`;
    expect(pluralSkWouldHaveProduced).toBe("Wybrane: 22 płytek");
    expect(pl22).not.toBe(pluralSkWouldHaveProduced);
  });
});

describe("AC-TERM-4 Czech tile vs letter and Polish płytk/literę", () => {
  it("keeps Czech kámen on the counted tile and písmeno on the blank letter", () => {
    for (const count of [0, 1, 2, 4, 5, 22, 25]) {
      const rendered = tf("cs", "controls.tilesSelected", { count });
      expect(rendered).toMatch(/kámen|kameny|kamenů/);
      expect(rendered).not.toContain("písmeno");
    }
    expect(t("cs", "blank.chooseLetter")).toContain("písmeno");
  });

  it("keeps Polish płytk* on the counted tile and literę on the blank letter", () => {
    for (const count of [0, 1, 2, 4, 5, 22, 25]) {
      expect(tf("pl", "controls.tilesSelected", { count })).toMatch(
        /płytka|płytki|płytek/,
      );
    }
    expect(t("pl", "blank.chooseLetter")).toContain("literę");
  });
});
