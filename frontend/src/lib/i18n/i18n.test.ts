import { describe, expect, it } from "vitest";

import SettingsPage from "@/app/settings/page";
import { formatUpdatedAt } from "@/components/game/GameHistoryPanel";
import { formatJoinedDate } from "@/components/game/ProfileModal";
import { variantDisplayName } from "@/components/settings/GameLanguagePanel";
import type { VariantSummary } from "@/lib/types";

import { t, tf } from "./index";
import {
  detectBrowserLocale,
  isLocale,
  localeSyncDecision,
  LOCALES,
} from "./locales";
import { csFn, csText } from "./messages.cs";
import {
  aiPassBodyKey,
  enFn,
  enText,
  lexiconRejectionKey,
} from "./messages.en";
import { plFn, plText } from "./messages.pl";
import { skFn, skText } from "./messages.sk";
import { pluralCs, pluralPl, pluralSk } from "./plural";

const {
  BOARD_THEME_CHOICES,
  STEP_CHOICES,
  TIMEOUT_CHOICES,
} = SettingsPage;

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

describe("AC-LEX-4 lexicon rejection follows lexicon_id", () => {
  const IDS = ["collins2019", "slovak", "czech", "polish"] as const;

  it("selects the matching message in every locale and does not call Czech Collins", () => {
    for (const locale of LOCALES) {
      for (const lexiconId of IDS) {
        const message = t(locale, lexiconRejectionKey(lexiconId));
        expect(message.length).toBeGreaterThan(0);
        if (lexiconId === "czech") {
          expect(message).not.toContain("Collins");
        }
        if (lexiconId === "collins2019") {
          expect(message).toContain("Collins");
        }
      }
      expect(t(locale, lexiconRejectionKey("slovak"))).toBe(
        t(locale, "game.lexicon.slovak"),
      );
      expect(t(locale, lexiconRejectionKey("polish"))).toBe(
        t(locale, "game.lexicon.polish"),
      );
    }
  });
});

describe("AC-LEX-UNK unknown lexicon_id", () => {
  it("selects game.lexicon.unknown and does not throw", () => {
    expect(() => lexiconRejectionKey("hungarian")).not.toThrow();
    expect(lexiconRejectionKey("hungarian")).toBe("game.lexicon.unknown");
    expect(lexiconRejectionKey(undefined)).toBe("game.lexicon.unknown");
    expect(lexiconRejectionKey(null)).toBe("game.lexicon.unknown");
    expect(lexiconRejectionKey("")).toBe("game.lexicon.unknown");
    for (const locale of LOCALES) {
      expect(t(locale, lexiconRejectionKey("nope"))).toBe(
        t(locale, "game.lexicon.unknown"),
      );
    }
  });
});

describe("AC-TOAST-DISC ai pass subtitle is not load-bearing prose", () => {
  it("selects the exchange subtitle for a Slovak exchange title that contains no 'exchanged'", () => {
    const message = t("sk", "game.toast.aiExchanged");
    expect(message).toBe("AI vymenilo písmená");
    expect(message.toLowerCase()).not.toContain("exchanged");
    expect(aiPassBodyKey({ passKind: "exchange" })).toBe(
      "game.toast.aiExchangedBody",
    );
    expect(t("sk", aiPassBodyKey({ passKind: "exchange" }))).toBe(
      "AI si obnovilo zásobník a spotrebovalo ťah.",
    );
  });

  it("selects the pass subtitle for a pass toast", () => {
    expect(aiPassBodyKey({ passKind: "pass" })).toBe(
      "game.toast.aiPassedBody",
    );
    expect(t("sk", aiPassBodyKey({ passKind: "pass" }))).toBe(
      "Nenašlo platný ťah — si na ťahu!",
    );
  });
});

describe("AC-HEADING-4 game.toast.invalidWordHeading", () => {
  it("renders singular at count 1 and plural at 2 and 5 in all four locales", () => {
    expect(tf("en", "game.toast.invalidWordHeading", { count: 1 })).toBe(
      "Invalid Word!",
    );
    expect(tf("en", "game.toast.invalidWordHeading", { count: 2 })).toBe(
      "Invalid Words!",
    );
    expect(tf("en", "game.toast.invalidWordHeading", { count: 5 })).toBe(
      "Invalid Words!",
    );
    expect(tf("sk", "game.toast.invalidWordHeading", { count: 1 })).toBe(
      "Neplatné slovo!",
    );
    expect(tf("sk", "game.toast.invalidWordHeading", { count: 2 })).toBe(
      "Neplatné slová!",
    );
    expect(tf("sk", "game.toast.invalidWordHeading", { count: 5 })).toBe(
      "Neplatné slová!",
    );
    expect(tf("cs", "game.toast.invalidWordHeading", { count: 1 })).toBe(
      "Neplatné slovo!",
    );
    expect(tf("cs", "game.toast.invalidWordHeading", { count: 2 })).toBe(
      "Neplatná slova!",
    );
    expect(tf("cs", "game.toast.invalidWordHeading", { count: 5 })).toBe(
      "Neplatná slova!",
    );
    expect(tf("pl", "game.toast.invalidWordHeading", { count: 1 })).toBe(
      "Nieprawidłowe słowo!",
    );
    expect(tf("pl", "game.toast.invalidWordHeading", { count: 2 })).toBe(
      "Nieprawidłowe słowa!",
    );
    expect(tf("pl", "game.toast.invalidWordHeading", { count: 5 })).toBe(
      "Nieprawidłowe słowa!",
    );
  });
});

describe("AC-ROUTEFAIL-4 game.ai.routeFailed* keys", () => {
  it("interpolates status in all four locales without English in sk/cs/pl", () => {
    for (const locale of LOCALES) {
      const failed = tf(locale, "game.ai.routeFailed", { status: 503 });
      const before = tf(locale, "game.ai.routeFailedBeforeStream", {
        status: 502,
      });
      const preview = tf(locale, "game.ai.routeFailedWithPreview", {
        status: 500,
        preview: "upstream timeout",
      });
      expect(failed).toContain("503");
      expect(before).toContain("502");
      expect(preview).toContain("500");
      expect(preview).toContain("upstream timeout");
      if (locale !== "en") {
        expect(failed.toLowerCase()).not.toContain("route failed");
        expect(before.toLowerCase()).not.toContain("route failed");
        expect(preview.toLowerCase()).not.toContain("route failed");
      }
    }
    expect(tf("en", "game.ai.routeFailed", { status: 418 })).toBe(
      "AI route failed (418).",
    );
    expect(tf("en", "game.ai.routeFailedBeforeStream", { status: 502 })).toBe(
      "AI route failed (502) before the stream started.",
    );
    expect(tf("en", "game.ai.routeFailedWithPreview", {
      status: 500,
      preview: "nope",
    })).toBe("AI route failed (500): nope");
  });
});

describe("AC-GAME-TERM Czech kámen and Polish płytki on the exchange prompt", () => {
  it("keeps Czech kameny not písmen, and Polish płytki", () => {
    const cs = t("cs", "game.status.selectExchange");
    expect(cs).toContain("kameny");
    expect(cs).not.toContain("písmen");
    expect(t("pl", "game.status.selectExchange")).toContain("płytki");
  });
});

const INSTALLED_VARIANTS = [
  "english",
  "slovak",
  "czech",
  "polish",
] as const;

function variantForSlug(slug: string, displayName: string): VariantSummary {
  return {
    slug,
    display_name: displayName,
    language_code: null,
    readiness: "playable",
  };
}

function queueLabel(
  locale: (typeof LOCALES)[number],
  variant: VariantSummary,
): string {
  return tf(locale, "play.humanQueue.queueFor", {
    variant: variantDisplayName(variant, (key) => t(locale, key)),
  });
}

describe("AC-QUEUE-VARIANT uii-01-F14 queue label follows the variant", () => {
  it("renders each installed variant's own name and never another variant's", () => {
    const ownName: Record<(typeof INSTALLED_VARIANTS)[number], Record<(typeof LOCALES)[number], string>> = {
      english: {
        en: "English",
        sk: "Angličtina",
        cs: "Angličtina",
        pl: "Angielski",
      },
      slovak: {
        en: "Slovak",
        sk: "Slovenčina",
        cs: "Slovenština",
        pl: "Słowacki",
      },
      czech: {
        en: "Czech",
        sk: "Čeština",
        cs: "Čeština",
        pl: "Czeski",
      },
      polish: {
        en: "Polish",
        sk: "Poľština",
        cs: "Polština",
        pl: "Polski",
      },
    };

    for (const locale of LOCALES) {
      for (const slug of INSTALLED_VARIANTS) {
        const label = queueLabel(
          locale,
          variantForSlug(slug, `NOT-${slug}`),
        );
        expect(label).toContain(ownName[slug][locale]);
        for (const other of INSTALLED_VARIANTS) {
          if (other === slug) continue;
          expect(label).not.toContain(ownName[other][locale]);
        }
      }
    }

    const czechSk = queueLabel("sk", variantForSlug("czech", "NOT-czech"));
    expect(czechSk).toContain("Čeština");
    expect(czechSk).not.toContain("Angličtina");
    expect(czechSk).not.toContain("Slovenčina");

    for (const locale of LOCALES) {
      expect(queueLabel(locale, variantForSlug("czech", "NOT-czech"))).not.toContain(
        "English",
      );
    }
  });
});

describe("AC-QUEUE-UNKNOWN unrecognised slug uses display_name", () => {
  it("does not throw and does not render another variant's name", () => {
    const unknown = variantForSlug("hungarian", "Magyar");
    expect(() =>
      variantDisplayName(unknown, (key) => t("sk", key)),
    ).not.toThrow();
    expect(variantDisplayName(unknown, (key) => t("sk", key))).toBe("Magyar");

    const label = queueLabel("sk", unknown);
    expect(label).toContain("Magyar");
    expect(label).not.toContain("Angličtina");
    expect(label).not.toContain("Slovenčina");
    expect(label).not.toContain("Čeština");
    expect(label).not.toContain("Poľština");
    expect(label).not.toBe("English queue");
    expect(label).not.toBe("Slovak queue");
  });
});

describe("AC-PLAY-4 lobby titles", () => {
  it("renders play.title, play.ai.title and play.humanQueue.title in all four locales", () => {
    expect(t("en", "play.title")).toBe("Choose the next board");
    expect(t("sk", "play.title")).toBe("Vyber si ďalšiu partiu");
    expect(t("cs", "play.title")).toBe("Vyber si další partii");
    expect(t("pl", "play.title")).toBe("Wybierz następną partię");

    expect(t("en", "play.ai.title")).toBe("Play the house");
    expect(t("sk", "play.ai.title")).toBe("Hraj proti AI");
    expect(t("cs", "play.ai.title")).toBe("Hraj proti AI");
    expect(t("pl", "play.ai.title")).toBe("Zagraj z AI");

    expect(t("en", "play.humanQueue.title")).toBe("Find a live opponent");
    expect(t("sk", "play.humanQueue.title")).toBe("Nájdi živého súpera");
    expect(t("cs", "play.humanQueue.title")).toBe("Najdi živého soupeře");
    expect(t("pl", "play.humanQueue.title")).toBe("Znajdź żywego rywala");
  });
});

describe("AC-QUEUE-ROOM-4 queue.room interpolates the code", () => {
  it("includes the code in all four locales and Slavic forms omit Room", () => {
    expect(tf("en", "queue.room", { code: "abcd1234" })).toBe("Room abcd1234");
    expect(tf("sk", "queue.room", { code: "abcd1234" })).toBe(
      "Miestnosť abcd1234",
    );
    expect(tf("cs", "queue.room", { code: "abcd1234" })).toBe(
      "Místnost abcd1234",
    );
    expect(tf("pl", "queue.room", { code: "abcd1234" })).toBe("Pokój abcd1234");
    expect(tf("sk", "queue.room", { code: "abcd1234" })).not.toContain("Room");
    expect(tf("cs", "queue.room", { code: "abcd1234" })).not.toContain("Room");
    expect(tf("pl", "queue.room", { code: "abcd1234" })).not.toContain("Room");
  });
});

const HEADER_KEYS = [
  "header.giveUp",
  "header.givingUp",
  "header.giveUpTooltip",
  "header.logout",
  "header.loggingOut",
  "header.backToBoards",
  "header.profile",
  "header.games",
] as const;

const HEADER_EXPECTED: Record<(typeof HEADER_KEYS)[number], Record<(typeof LOCALES)[number], string>> = {
  "header.giveUp": {
    en: "Give up",
    sk: "Vzdať sa",
    cs: "Vzdát se",
    pl: "Poddaj się",
  },
  "header.givingUp": {
    en: "Giving up...",
    sk: "Vzdávam sa...",
    cs: "Vzdávám se...",
    pl: "Poddaję się...",
  },
  "header.giveUpTooltip": {
    en: "Give up current game",
    sk: "Vzdať túto partiu",
    cs: "Vzdát tuto partii",
    pl: "Poddaj tę partię",
  },
  "header.logout": {
    en: "Logout",
    sk: "Odhlásiť sa",
    cs: "Odhlásit se",
    pl: "Wyloguj się",
  },
  "header.loggingOut": {
    en: "Logging out...",
    sk: "Odhlasujem...",
    cs: "Odhlašuji...",
    pl: "Wylogowuję...",
  },
  "header.backToBoards": {
    en: "Back to boards",
    sk: "Späť na partie",
    cs: "Zpět na partie",
    pl: "Powrót do partii",
  },
  "header.profile": {
    en: "Profile",
    sk: "Profil",
    cs: "Profil",
    pl: "Profil",
  },
  "header.games": {
    en: "Games",
    sk: "Partie",
    cs: "Partie",
    pl: "Partie",
  },
};

describe("AC-HEADER-4 header.* keys", () => {
  it("renders the eight header keys as the authored string in all four locales", () => {
    for (const key of HEADER_KEYS) {
      for (const locale of LOCALES) {
        expect(t(locale, key)).toBe(HEADER_EXPECTED[key][locale]);
      }
    }
  });
});

const OVERLAY_KEYS = [
  "overlay.aiThinking",
  "overlay.searching",
  "overlay.best",
  "overlay.bestBadge",
  "overlay.filtering",
] as const;

const OVERLAY_EXPECTED: Record<(typeof OVERLAY_KEYS)[number], Record<(typeof LOCALES)[number], string>> = {
  "overlay.aiThinking": {
    en: "AI Thinking",
    sk: "AI premýšľa",
    cs: "AI přemýšlí",
    pl: "AI myśli",
  },
  "overlay.searching": {
    en: "Searching for moves...",
    sk: "Hľadám ťahy...",
    cs: "Hledám tahy...",
    pl: "Szukam ruchów...",
  },
  "overlay.best": {
    en: "Best",
    sk: "Najlepší",
    cs: "Nejlepší",
    pl: "Najlepszy",
  },
  "overlay.bestBadge": {
    en: "BEST",
    sk: "NAJLEPŠÍ",
    cs: "NEJLEPŠÍ",
    pl: "NAJLEPSZY",
  },
  "overlay.filtering": {
    en: "Filtering weak or invalid lines before showing a serious move...",
    sk: "Odfiltrúvam slabé a neplatné ťahy, kým nenájdem vážny ťah...",
    cs: "Odfiltrovávám slabé a neplatné tahy, dokud nenajdu vážný tah...",
    pl: "Odfiltrowuję słabe i nieprawidłowe ruchy, aż znajdę poważny ruch...",
  },
};

describe("AC-OVERLAY-4 overlay.* keys", () => {
  it("renders the five overlay keys as the authored string in all four locales", () => {
    for (const key of OVERLAY_KEYS) {
      for (const locale of LOCALES) {
        expect(t(locale, key)).toBe(OVERLAY_EXPECTED[key][locale]);
      }
    }
  });
});

describe("AC-BADGE-CASE overlay.bestBadge is catalog-uppercase", () => {
  it("equals its own uppercase form in every locale, and overlay.best does not in sk/cs/pl", () => {
    for (const locale of LOCALES) {
      const badge = t(locale, "overlay.bestBadge");
      expect(badge).toBe(badge.toUpperCase());
    }
    for (const locale of ["sk", "cs", "pl"] as const) {
      const best = t(locale, "overlay.best");
      expect(best).not.toBe(best.toUpperCase());
    }
  });
});

describe("AC-NO-TELEMETRY-KEY en catalog excludes overlay telemetry prose", () => {
  it("contains none of the telemetry fragments providers exhausted, dead rack, or legal rescue", () => {
    const fragments = ["providers exhausted", "dead rack", "legal rescue"];
    for (const value of Object.values(enText)) {
      const lower = value.toLowerCase();
      for (const fragment of fragments) {
        expect(lower).not.toContain(fragment);
      }
    }
  });
});

describe("AC-DATE-LOCALE saved-board dates follow the interface locale", () => {
  it("keeps en-US output pinned and uses 24-hour localized output for sk/cs/pl", () => {
    const timestamp = "2026-09-02T16:35:00";
    const english = formatUpdatedAt(timestamp, "en");

    expect(english).toBe("Sep 2, 4:35 PM");
    for (const locale of ["sk", "cs", "pl"] as const) {
      const localized = formatUpdatedAt(timestamp, locale);
      expect(localized).not.toBe(english);
      expect(localized).not.toMatch(/\b(?:AM|PM)\b/);
    }

    expect(formatUpdatedAt("not-a-date", "en")).toBe("Unknown");
    expect(formatUpdatedAt("not-a-date", "sk")).toBe("Neznáme");
    expect(formatUpdatedAt("not-a-date", "cs")).toBe("Neznámé");
    expect(formatUpdatedAt("not-a-date", "pl")).toBe("Nieznane");
  });
});

describe("AC-JOINED-LOCALE profile joined date follows the interface locale", () => {
  it("keeps en-US output pinned and removes the English month from sk/cs/pl", () => {
    const timestamp = "2026-09-02T12:00:00Z";
    const english = formatJoinedDate(timestamp, "en");

    expect(english).toBe("September 2, 2026");
    for (const locale of ["sk", "cs", "pl"] as const) {
      const localized = formatJoinedDate(timestamp, locale);
      expect(localized).not.toBe(english);
      expect(localized).not.toContain("September");
    }
  });
});

describe("AC-JOINED-INVALID profile joined date uses the localized fallback", () => {
  it("returns the active locale's history.unknownDate for null and invalid values", () => {
    for (const value of [null, "not-a-date"] as const) {
      expect(formatJoinedDate(value, "en")).toBe("Unknown");
      expect(formatJoinedDate(value, "sk")).toBe("Neznáme");
      expect(formatJoinedDate(value, "cs")).toBe("Neznámé");
      expect(formatJoinedDate(value, "pl")).toBe("Nieznane");
    }
  });
});

const PROFILE_EXPECTED = {
  "profile.subtitle": {
    en: "Account details and password security in one place.",
    sk: "Údaje o účte a bezpečnosť hesla na jednom mieste.",
    cs: "Údaje o účtu a bezpečnost hesla na jednom místě.",
    pl: "Dane konta i bezpieczeństwo hasła w jednym miejscu.",
  },
  "profile.email": { en: "Email", sk: "Email", cs: "Email", pl: "Email" },
  "profile.noEmail": {
    en: "No email set",
    sk: "Email nie je nastavený",
    cs: "Email není nastavený",
    pl: "Email nie jest ustawiony",
  },
  "profile.memberSince": {
    en: "Member since",
    sk: "Členom od",
    cs: "Členem od",
    pl: "Członkiem od",
  },
  "profile.password.subtitle": {
    en: "Update your login password without leaving the game.",
    sk: "Zmeň si prihlasovacie heslo bez toho, aby si opustil hru.",
    cs: "Změň si přihlašovací heslo bez toho, abys opustil hru.",
    pl: "Zmień hasło do logowania bez opuszczania gry.",
  },
  "profile.password.footnote": {
    en: "Stronger passwords make multiplayer accounts safer.",
    sk: "Silnejšie heslo lepšie chráni tvoj účet v hre proti ľuďom.",
    cs: "Silnější heslo lépe chrání tvůj účet ve hře proti lidem.",
    pl: "Silniejsze hasło lepiej chroni twoje konto w grze z ludźmi.",
  },
  "profile.field.current": {
    en: "Current password",
    sk: "Súčasné heslo",
    cs: "Současné heslo",
    pl: "Aktualne hasło",
  },
  "profile.field.new": {
    en: "New password",
    sk: "Nové heslo",
    cs: "Nové heslo",
    pl: "Nowe hasło",
  },
  "profile.field.confirm": {
    en: "Confirm new password",
    sk: "Potvrď nové heslo",
    cs: "Potvrď nové heslo",
    pl: "Potwierdź nowe hasło",
  },
  "profile.ph.current": {
    en: "Current password",
    sk: "Súčasné heslo",
    cs: "Současné heslo",
    pl: "Aktualne hasło",
  },
  "profile.ph.new": {
    en: "At least 8 characters",
    sk: "Aspoň 8 znakov",
    cs: "Alespoň 8 znaků",
    pl: "Co najmniej 8 znaków",
  },
  "profile.ph.confirm": {
    en: "Repeat new password",
    sk: "Zopakuj nové heslo",
    cs: "Zopakuj nové heslo",
    pl: "Powtórz nowe hasło",
  },
  "profile.submit": {
    en: "Update password",
    sk: "Zmeniť heslo",
    cs: "Změnit heslo",
    pl: "Zmień hasło",
  },
  "profile.submitting": {
    en: "Updating...",
    sk: "Mením...",
    cs: "Měním...",
    pl: "Zmieniam...",
  },
  "profile.error.allFields": {
    en: "Fill in all password fields.",
    sk: "Vyplň všetky polia s heslom.",
    cs: "Vyplň všechna pole s heslem.",
    pl: "Wypełnij wszystkie pola hasła.",
  },
  "profile.error.mismatch": {
    en: "New passwords do not match.",
    sk: "Nové heslá sa nezhodujú.",
    cs: "Nová hesla se neshodují.",
    pl: "Nowe hasła nie są zgodne.",
  },
} as const;

describe("AC-PROFILE-4 profile catalog", () => {
  it("renders all sixteen authored strings in all four locales", () => {
    for (const key of Object.keys(PROFILE_EXPECTED) as Array<
      keyof typeof PROFILE_EXPECTED
    >) {
      for (const locale of LOCALES) {
        expect(t(locale, key)).toBe(PROFILE_EXPECTED[key][locale]);
      }
    }
  });
});

describe("AC-PROFILE-DUP intentional profile catalog duplicates", () => {
  it("keeps current-password label and placeholder equal and Email unchanged", () => {
    for (const locale of LOCALES) {
      expect(t(locale, "profile.field.current")).toBe(
        t(locale, "profile.ph.current"),
      );
      expect(t(locale, "profile.email")).toBe("Email");
    }
  });
});

const HISTORY_EXPECTED = {
  "history.col.rival": { en: "Rival", sk: "Súper", cs: "Soupeř", pl: "Rywal" },
  "history.col.mode": { en: "Mode", sk: "Režim", cs: "Režim", pl: "Tryb" },
  "history.col.result": {
    en: "Result",
    sk: "Výsledok",
    cs: "Výsledek",
    pl: "Wynik",
  },
  "history.col.score": { en: "Score", sk: "Skóre", cs: "Skóre", pl: "Wynik" },
  "history.col.moves": { en: "Moves", sk: "Ťahy", cs: "Tahy", pl: "Ruchy" },
  "history.col.updated": {
    en: "Updated",
    sk: "Zmenené",
    cs: "Změněno",
    pl: "Zmienione",
  },
  "history.outcome.waiting": {
    en: "Waiting",
    sk: "Čaká sa",
    cs: "Čeká se",
    pl: "Oczekiwanie",
  },
  "history.outcome.active": {
    en: "In progress",
    sk: "Prebieha",
    cs: "Probíhá",
    pl: "W toku",
  },
  "history.outcome.won": {
    en: "Won",
    sk: "Vyhral si",
    cs: "Vyhrál jsi",
    pl: "Wygrałeś",
  },
  "history.outcome.lost": {
    en: "Lost",
    sk: "Prehral si",
    cs: "Prohrál jsi",
    pl: "Przegrałeś",
  },
  "history.outcome.draw": { en: "Draw", sk: "Remíza", cs: "Remíza", pl: "Remis" },
  "history.outcome.gaveUp": {
    en: "Gave up",
    sk: "Vzdal si sa",
    cs: "Vzdal jsi se",
    pl: "Poddałeś się",
  },
  "history.outcome.abandoned": {
    en: "Abandoned",
    sk: "Opustená",
    cs: "Opuštěná",
    pl: "Porzucona",
  },
  "history.outcome.unknown": {
    en: "Unknown",
    sk: "Neznámy",
    cs: "Neznámý",
    pl: "Nieznany",
  },
} as const;

describe("AC-HISTORY-4 history columns and outcomes", () => {
  it("renders every authored column and outcome string in all four locales", () => {
    for (const [key, expected] of Object.entries(HISTORY_EXPECTED)) {
      for (const locale of LOCALES) {
        expect(t(locale, key as keyof typeof enText)).toBe(expected[locale]);
      }
    }
  });
});

describe("AC-PAGING-4 saved-board pagination", () => {
  it("interpolates both summaries in all four locales without games in Slavic showing copy", () => {
    const expected = {
      en: { pageOf: "Page 2 of 7", showing: "Showing 11-20 of 63 games" },
      sk: { pageOf: "Strana 2 z 7", showing: "Zobrazené 11-20 z 63" },
      cs: { pageOf: "Strana 2 z 7", showing: "Zobrazeno 11-20 z 63" },
      pl: { pageOf: "Strona 2 z 7", showing: "Pokazane 11-20 z 63" },
    } as const;

    for (const locale of LOCALES) {
      expect(tf(locale, "history.pageOf", { page: 2, total: 7 })).toBe(
        expected[locale].pageOf,
      );
      const showing = tf(locale, "history.showing", {
        from: 11,
        to: 20,
        total: 63,
      });
      expect(showing).toBe(expected[locale].showing);
      if (locale !== "en") expect(showing).not.toContain("games");
    }
  });
});

describe("AC-POLISH-DUP history result and score headings", () => {
  it("deliberately uses Wynik for both Polish columns", () => {
    expect(t("pl", "history.col.result")).toBe("Wynik");
    expect(t("pl", "history.col.score")).toBe("Wynik");
  });
});

const SETTINGS_EXPECTED = {
  "settings.timeout.30": {
    en: "Fast board read",
    sk: "Rýchle prečítanie plochy",
    cs: "Rychlé přečtení desky",
    pl: "Szybkie odczytanie planszy",
  },
  "settings.timeout.60": {
    en: "Balanced search",
    sk: "Vyvážené hľadanie",
    cs: "Vyvážené hledání",
    pl: "Wyważone szukanie",
  },
  "settings.timeout.120": {
    en: "Default thinking time",
    sk: "Predvolený čas na rozmýšľanie",
    cs: "Výchozí čas na rozmýšlení",
    pl: "Domyślny czas myślenia",
  },
  "settings.timeout.180": {
    en: "Tournament pace",
    sk: "Turnajové tempo",
    cs: "Turnajové tempo",
    pl: "Tempo turniejowe",
  },
  "settings.timeout.300": {
    en: "Longest think",
    sk: "Najdlhšie rozmýšľanie",
    cs: "Nejdelší rozmýšlení",
    pl: "Najdłuższe myślenie",
  },
  "settings.steps.10": {
    en: "Quick tools",
    sk: "Rýchly priebeh",
    cs: "Rychlý průběh",
    pl: "Szybki przebieg",
  },
  "settings.steps.20": {
    en: "More tries",
    sk: "Viac pokusov",
    cs: "Více pokusů",
    pl: "Więcej prób",
  },
  "settings.steps.30": {
    en: "Focused search",
    sk: "Zamerané hľadanie",
    cs: "Zaměřené hledání",
    pl: "Skoncentrowane szukanie",
  },
  "settings.steps.50": {
    en: "Default search depth",
    sk: "Predvolená hĺbka hľadania",
    cs: "Výchozí hloubka hledání",
    pl: "Domyślna głębokość szukania",
  },
  "settings.steps.80": {
    en: "Max pressure",
    sk: "Maximálny tlak",
    cs: "Maximální tlak",
    pl: "Maksymalny nacisk",
  },
  "settings.board.wood": {
    en: "Wood",
    sk: "Drevo",
    cs: "Dřevo",
    pl: "Drewno",
  },
  "settings.board.black": {
    en: "Black",
    sk: "Čierna",
    cs: "Černá",
    pl: "Czarny",
  },
  "settings.board.green": {
    en: "Green",
    sk: "Zelená",
    cs: "Zelená",
    pl: "Zielony",
  },
} as const;

describe("AC-SETTINGS-4 settings choice copy", () => {
  it("renders timeout, step, and board labels exactly in all four locales", () => {
    for (const [key, expected] of Object.entries(SETTINGS_EXPECTED)) {
      for (const locale of LOCALES) {
        expect(t(locale, key as keyof typeof enText)).toBe(expected[locale]);
      }
    }
  });
});

const TOGGLE_EXPECTED = {
  "settings.toggle.on": {
    en: "On",
    sk: "Zapnuté",
    cs: "Zapnuto",
    pl: "Włączone",
  },
  "settings.toggle.off": {
    en: "Off",
    sk: "Vypnuté",
    cs: "Vypnuto",
    pl: "Wyłączone",
  },
  "settings.shiny.onDesc": {
    en: "Animated board sheen",
    sk: "Animovaný lesk plochy",
    cs: "Animovaný lesk desky",
    pl: "Animowany błysk planszy",
  },
  "settings.shiny.offDesc": {
    en: "Lower GPU load",
    sk: "Menšia záťaž GPU",
    cs: "Menší zátěž GPU",
    pl: "Mniejsze obciążenie GPU",
  },
  "settings.premium.onDesc": {
    en: "Premium interactive panels",
    sk: "Interaktívne premium panely",
    cs: "Interaktivní premium panely",
    pl: "Interaktywne panele premium",
  },
  "settings.premium.offDesc": {
    en: "Classic dark surfaces",
    sk: "Klasické tmavé povrchy",
    cs: "Klasické tmavé povrchy",
    pl: "Klasyczne ciemne powierzchnie",
  },
} as const;

describe("AC-TOGGLE-4 shared labels and distinct descriptions", () => {
  it("renders the authored toggle copy and keeps all four descriptions distinct", () => {
    for (const [key, expected] of Object.entries(TOGGLE_EXPECTED)) {
      for (const locale of LOCALES) {
        expect(t(locale, key as keyof typeof enText)).toBe(expected[locale]);
      }
    }
    const descriptionKeys = [
      "settings.shiny.onDesc",
      "settings.shiny.offDesc",
      "settings.premium.onDesc",
      "settings.premium.offDesc",
    ] as const;
    for (const locale of LOCALES) {
      expect(new Set(descriptionKeys.map((key) => t(locale, key))).size).toBe(4);
    }
  });
});

describe("AC-STATS-4 overlay stats", () => {
  it("interpolates count in every locale without English status words in Slavic copy", () => {
    const keys = [
      "overlay.stats.tried",
      "overlay.stats.valid",
      "overlay.stats.rejected",
    ] as const;
    for (const locale of LOCALES) {
      for (const key of keys) {
        expect(tf(locale, key, { count: 3 })).toContain("3");
      }
    }
    expect(tf("sk", "overlay.stats.tried", { count: 3 })).toBe("Skúsené: 3");
    expect(tf("sk", "overlay.stats.valid", { count: 3 })).toBe("Platné: 3");
    expect(tf("sk", "overlay.stats.rejected", { count: 3 })).toBe(
      "Zamietnuté: 3",
    );
    for (const locale of ["sk", "cs", "pl"] as const) {
      for (const key of keys) {
        expect(tf(locale, key, { count: 3 }).toLowerCase()).not.toMatch(
          /tried|valid|rejected/,
        );
      }
    }
  });
});

describe("AC-PICKER-COPY picker catalog", () => {
  it("keeps the four picker chrome strings byte-identical to the authored table", () => {
    expect(t("en", "picker.search")).toBe("Search");
    expect(t("sk", "picker.search")).toBe("Hľadať");
    expect(t("cs", "picker.search")).toBe("Hledat");
    expect(t("pl", "picker.search")).toBe("Szukaj");
    expect(t("en", "picker.noMatch")).toBe("No match");
    expect(t("sk", "picker.noMatch")).toBe("Žiadna zhoda");
    expect(t("cs", "picker.noMatch")).toBe("Žádná shoda");
    expect(t("pl", "picker.noMatch")).toBe("Brak dopasowania");
    expect(t("en", "picker.uiLanguageLabel")).toBe(
      t("en", "settings.uiLanguage.title"),
    );
    expect(t("sk", "picker.uiLanguageLabel")).toBe(
      t("sk", "settings.uiLanguage.title"),
    );
    expect(t("cs", "picker.uiLanguageLabel")).toBe(
      t("cs", "settings.uiLanguage.title"),
    );
    expect(t("pl", "picker.uiLanguageLabel")).toBe(
      t("pl", "settings.uiLanguage.title"),
    );
    expect(t("en", "picker.gameVariantLabel")).toBe(
      t("en", "settings.gameVariant.title"),
    );
    expect(t("sk", "picker.gameVariantLabel")).toBe(
      t("sk", "settings.gameVariant.title"),
    );
    expect(t("cs", "picker.gameVariantLabel")).toBe(
      t("cs", "settings.gameVariant.title"),
    );
    expect(t("pl", "picker.gameVariantLabel")).toBe(
      t("pl", "settings.gameVariant.title"),
    );
    expect(tf("en", "picker.flagAlt", { language: "Slovenčina" })).toBe(
      "Slovenčina flag",
    );
    expect(tf("sk", "picker.flagAlt", { language: "Slovenčina" })).toBe(
      "Vlajka: Slovenčina",
    );
    expect(tf("cs", "picker.flagAlt", { language: "Slovenčina" })).toBe(
      "Vlajka: Slovenčina",
    );
    expect(tf("pl", "picker.flagAlt", { language: "Slovenčina" })).toBe(
      "Flaga: Slovenčina",
    );
  });
});

describe("AC-KEYTYPED settings option keys", () => {
  it("resolves every constant-array key to non-empty copy in all four locales", () => {
    const textKeys = [
      ...TIMEOUT_CHOICES.map((choice) =>
        "descriptionKey" in choice ? choice.descriptionKey : undefined,
      ),
      ...STEP_CHOICES.map((choice) =>
        "descriptionKey" in choice ? choice.descriptionKey : undefined,
      ),
      ...BOARD_THEME_CHOICES.flatMap((choice) => [
        "labelKey" in choice ? choice.labelKey : undefined,
        "descriptionKey" in choice ? choice.descriptionKey : undefined,
      ]),
    ];
    for (const key of textKeys) {
      expect(key).toBeDefined();
      for (const locale of LOCALES) {
        expect(t(locale, key!)).not.toBe("");
      }
    }
  });
});
