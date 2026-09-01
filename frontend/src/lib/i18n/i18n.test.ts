import { describe, expect, it } from "vitest";
import { tf } from "./index";
import { detectBrowserLocale } from "./locales";
import { enFn, enText } from "./messages.en";
import { skFn, skText } from "./messages.sk";
import { pluralSk } from "./plural";

const ENUMERATION_FRAGMENTS = [
  "neexistuje",
  "nenájden",
  "nesprávne heslo",
  "wrong password",
  "unknown user",
];

describe("AC-DETECT detectBrowserLocale", () => {
  it("returns sk for Slovak tags and en otherwise", () => {
    expect(detectBrowserLocale(["sk"])).toBe("sk");
    expect(detectBrowserLocale(["sk-SK"])).toBe("sk");
    expect(detectBrowserLocale(["SK"])).toBe("sk");
    expect(detectBrowserLocale(["sk-SK", "en"])).toBe("sk");
    expect(detectBrowserLocale(["en-US"])).toBe("en");
    expect(detectBrowserLocale(["cs-CZ"])).toBe("en");
    expect(detectBrowserLocale(["sks"])).toBe("en");
    expect(detectBrowserLocale([])).toBe("en");
  });
});

describe("AC-EXHAUST catalogs share one key set", () => {
  it("matches en/sk text and function keys at runtime", () => {
    expect(Object.keys(skText).sort()).toEqual(Object.keys(enText).sort());
    expect(Object.keys(skFn).sort()).toEqual(Object.keys(enFn).sort());
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

describe("AC-SEC message catalogs", () => {
  it("keeps the Slovak login 401 free of user-enumeration fragments", () => {
    const login = skText["error.invalidCredentials"];
    expect(login).toBe("Nesprávne používateľské meno alebo heslo");
    for (const fragment of ENUMERATION_FRAGMENTS) {
      expect(login.toLowerCase()).not.toContain(fragment);
    }
    expect(skText["error.sessionExpired"]).toBe(
      "Prihlásenie vypršalo. Prihlás sa znova.",
    );
    expect(skText["error.sessionExpired"]).not.toBe(login);
  });
});
