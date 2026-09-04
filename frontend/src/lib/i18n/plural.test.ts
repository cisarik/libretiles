import { describe, expect, it } from "vitest";

import {
  pluralAf,
  pluralCs,
  pluralDa,
  pluralDe,
  pluralEn,
  pluralIs,
  pluralIt,
  pluralNl,
  pluralPl,
  pluralPt,
  pluralSk,
  pluralSv,
} from "./plural";

// An executable pin on the twelve helpers against the runtime's own CLDR data,
// so a CLDR change becomes a red test instead of a silently wrong string.
//
// Distinct SENTINELS, not real words: the assertion is about which SLOT the
// helper chose, and a real noun would let a coincidence pass.
const SLOT = {
  one: "<slot:one>",
  few: "<slot:few>",
  many: "<slot:many>",
  other: "<slot:other>",
} as const;

type PluralCategory = "zero" | "one" | "two" | "few" | "many" | "other";

type PluralCase = {
  readonly lang: string;
  readonly language: string;
  readonly helper: string;
  readonly invoke: (n: number) => string;
  // Explicitly declared SLOT -> CLDR CATEGORY map. Never inferred from a
  // parameter name: pluralSk's third parameter is named `many` while over the
  // integers CLDR Slovak has no `many` at all.
  readonly category: Readonly<Record<string, PluralCategory>>;
};

const TWO_SLOT: Readonly<Record<string, PluralCategory>> = {
  [SLOT.one]: "one",
  [SLOT.other]: "other",
};

const CASES: readonly PluralCase[] = [
  {
    lang: "en",
    language: "English",
    helper: "pluralEn",
    invoke: (n) => pluralEn(n, SLOT.one, SLOT.other),
    category: TWO_SLOT,
  },
  {
    lang: "af",
    language: "Afrikaans",
    helper: "pluralAf",
    invoke: (n) => pluralAf(n, SLOT.one, SLOT.other),
    category: TWO_SLOT,
  },
  {
    lang: "nl",
    language: "Dutch",
    helper: "pluralNl",
    invoke: (n) => pluralNl(n, SLOT.one, SLOT.other),
    category: TWO_SLOT,
  },
  {
    lang: "de",
    language: "German",
    helper: "pluralDe",
    invoke: (n) => pluralDe(n, SLOT.one, SLOT.other),
    category: TWO_SLOT,
  },
  {
    lang: "da",
    language: "Danish",
    helper: "pluralDa",
    invoke: (n) => pluralDa(n, SLOT.one, SLOT.other),
    category: TWO_SLOT,
  },
  {
    lang: "sv",
    language: "Swedish",
    helper: "pluralSv",
    invoke: (n) => pluralSv(n, SLOT.one, SLOT.other),
    category: TWO_SLOT,
  },
  {
    lang: "is",
    language: "Icelandic",
    helper: "pluralIs",
    invoke: (n) => pluralIs(n, SLOT.one, SLOT.other),
    category: TWO_SLOT,
  },
  {
    lang: "it",
    language: "Italian",
    helper: "pluralIt",
    invoke: (n) => pluralIt(n, SLOT.one, SLOT.other, SLOT.many),
    category: {
      [SLOT.one]: "one",
      [SLOT.other]: "other",
      [SLOT.many]: "many",
    },
  },
  {
    lang: "pt",
    language: "Portuguese",
    helper: "pluralPt",
    invoke: (n) => pluralPt(n, SLOT.one, SLOT.other, SLOT.many),
    category: {
      [SLOT.one]: "one",
      [SLOT.other]: "other",
      [SLOT.many]: "many",
    },
  },
  {
    lang: "sk",
    language: "Slovak",
    helper: "pluralSk",
    invoke: (n) => pluralSk(n, SLOT.one, SLOT.few, SLOT.many),
    // The third slot is NAMED `many` and is CLDR `other`: over the integers
    // CLDR Slovak has no `many`, and that slot holds the genitive plural, which
    // is the right form for 0 and 5+.
    category: {
      [SLOT.one]: "one",
      [SLOT.few]: "few",
      [SLOT.many]: "other",
    },
  },
  {
    lang: "cs",
    language: "Czech",
    helper: "pluralCs",
    invoke: (n) => pluralCs(n, SLOT.one, SLOT.few, SLOT.many),
    // Same slot naming as Slovak, and pluralCs is deliberately the same
    // function: sk and cs agree over the whole domain, fractions included.
    category: {
      [SLOT.one]: "one",
      [SLOT.few]: "few",
      [SLOT.many]: "other",
    },
  },
  {
    lang: "pl",
    language: "Polish",
    helper: "pluralPl",
    invoke: (n) => pluralPl(n, SLOT.one, SLOT.few, SLOT.many),
    // Polish is genuinely different from Slovak and Czech here: CLDR pl really
    // does have `many`, and pl 0 selects it.
    category: {
      [SLOT.one]: "one",
      [SLOT.few]: "few",
      [SLOT.many]: "many",
    },
  },
];

const SAMPLE_N: readonly number[] = [
  ...Array.from({ length: 3001 }, (_, i) => i),
  1_000_000,
  2_000_000,
  3_000_000,
  1_000_001,
];

const LANGS = CASES.map((c) => c.lang);
const SUPPORTED = new Set(Intl.PluralRules.supportedLocalesOf(LANGS));
const MISSING = LANGS.filter((lang) => !SUPPORTED.has(lang));
const RUNTIME = `node ${process.version} / ICU ${process.versions.icu ?? "unknown"}`;

// A small-icu Node build carries English only and would fail every non-English
// case for a reason that has nothing to do with this code.
const SKIP_NOTE =
  MISSING.length === 0
    ? ""
    : ` [SKIPPED: ${RUNTIME} has no Intl.PluralRules data for ${MISSING.join(", ")}]`;

describe("plural helpers pin CLDR over the integer domain", () => {
  it(`declares one case per exported helper on ${RUNTIME}`, () => {
    expect(CASES).toHaveLength(12);
    expect(new Set(LANGS).size).toBe(12);
    expect(new Set(CASES.map((c) => c.helper)).size).toBe(12);
  });

  for (const testCase of CASES) {
    it.skipIf(MISSING.length > 0)(
      `${testCase.helper} (${testCase.language}) matches Intl.PluralRules("${testCase.lang}")${SKIP_NOTE}`,
      () => {
        const rules = new Intl.PluralRules(testCase.lang);
        const mismatches: string[] = [];
        for (const n of SAMPLE_N) {
          const slot = testCase.invoke(n);
          const chosen = testCase.category[slot] ?? `UNMAPPED(${slot})`;
          const expected: string = rules.select(n);
          if (chosen !== expected) {
            mismatches.push(`n=${n}: helper chose ${chosen}, CLDR says ${expected}`);
          }
        }
        expect(
          mismatches.slice(0, 8),
          `${testCase.helper} (${testCase.language}, locale "${testCase.lang}") disagrees with CLDR ` +
            `at ${mismatches.length} of ${SAMPLE_N.length} sampled counts on ${RUNTIME}. ` +
            `Either the helper is wrong or CLDR changed.`,
        ).toEqual([]);
      },
    );
  }
});
