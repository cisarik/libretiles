import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { foldForSearch } from "@/lib/i18n/locales";

import {
  filterPickerOptions,
  nextPickerHighlight,
  PremiumPicker,
  type PremiumPickerOption,
} from "./PremiumPicker";

// The twelve shipped interface-language endonyms, in LOCALES order, each with the flag that now
// exists for it under frontend/public/. This fixture mirrors the shipping configuration exactly.
const ENDONYMS: readonly PremiumPickerOption[] = [
  { value: "en", label: "English", flagSrc: "/en.png" },
  { value: "sk", label: "Slovenčina", flagSrc: "/sk.png" },
  { value: "cs", label: "Čeština", flagSrc: "/cs.png" },
  { value: "pl", label: "Polski", flagSrc: "/pl.png" },
  { value: "de", label: "Deutsch", flagSrc: "/de.png" },
  { value: "pt", label: "Português", flagSrc: "/pt.png" },
  { value: "is", label: "Íslenska", flagSrc: "/is.png" },
  { value: "it", label: "Italiano", flagSrc: "/it.png" },
  { value: "nl", label: "Nederlands", flagSrc: "/nl.png" },
  { value: "da", label: "Dansk", flagSrc: "/da.png" },
  { value: "sv", label: "Svenska", flagSrc: "/sv.png" },
  { value: "af", label: "Afrikaans", flagSrc: "/af.png" },
];

// ⛔ THE FLAGLESS PATH MUST STAY COVERED EVEN THOUGH NOTHING SHIPS IT TODAY. `flagSrc` is optional
// on PremiumPickerOption, and the GAME-VARIANT picker still reaches this path for any variant slug
// absent from VARIANT_FLAG_SRC. A fixture that only ever supplies a flag would leave the conditional
// render untested and let a future thirteenth locale or variant regress it silently.
const MIXED_FLAGS: readonly PremiumPickerOption[] = [
  { value: "en", label: "English", flagSrc: "/en.png" },
  { value: "xx", label: "Ruritanian" },
  { value: "sk", label: "Slovenčina", flagSrc: "/sk.png" },
];

describe("AC-FOLD foldForSearch", () => {
  it("folds every diacritic the twelve shipped catalogs use, including the letters NFD cannot fold", () => {
    expect(foldForSearch("Čeština")).toBe("cestina");
    expect(foldForSearch("Slovenčina")).toBe("slovencina");
    expect(foldForSearch("Poľština")).toBe("polstina");
    expect(foldForSearch("Angličtina")).toBe("anglictina");
    expect(foldForSearch("Słowacki")).toBe("slowacki");
    expect(foldForSearch("Polski")).toBe("polski");
    expect(foldForSearch("Zamietnuté")).toBe("zamietnute");
    expect(foldForSearch("Ł")).toBe("l");
    expect(foldForSearch("ł")).toBe("l");
    expect(foldForSearch("Đ")).toBe("d");
    expect(foldForSearch("đ")).toBe("d");
    expect(foldForSearch("Ø")).toBe("o");
    expect(foldForSearch("ø")).toBe("o");

    // The regression: two shipped messages.is.ts game-variant labels that no ASCII query could
    // reach, because the fold left them as "þyska" and "sænska".
    expect(foldForSearch("Þýska")).toBe("thyska");
    expect(foldForSearch("Sænska")).toBe("saenska");

    expect(foldForSearch("Æ")).toBe("ae");
    expect(foldForSearch("æ")).toBe("ae");
    expect(foldForSearch("Þ")).toBe("th");
    expect(foldForSearch("þ")).toBe("th");
    expect(foldForSearch("Ð")).toBe("d");
    expect(foldForSearch("ð")).toBe("d");
    expect(foldForSearch("Œ")).toBe("oe");
    expect(foldForSearch("œ")).toBe("oe");
    expect(foldForSearch("ß")).toBe("ss");
    expect(foldForSearch("ı")).toBe("i");

    // ð U+00F0 ETH and đ U+0111 D-STROKE are different letters that look alike in many fonts and
    // both fold to "d". Escaped deliberately: this expectation is about codepoints, and it fails
    // if a later edit drops either entry instead of silently collapsing the two.
    expect(foldForSearch("\u00F0\u0111\u00D0\u0110")).toBe("dddd");

    // Word level, because a single-letter assertion would pass even if the defect survived in
    // real labels: one word per new letter from the campaign's target languages.
    expect(foldForSearch("maður")).toBe("madur");
    expect(foldForSearch("Kærlighed")).toBe("kaerlighed");
    expect(foldForSearch("Straße")).toBe("strasse");
    expect(foldForSearch("cœur")).toBe("coeur");
    expect(foldForSearch("Işık")).toBe("isik");
  });
});

describe("AC-FOLD-MATCH query matching", () => {
  it("matches the Cooperator's Čeština example in every case and accent variant", () => {
    const labels = ENDONYMS.map((option) => option.label);
    const cestinaHits = ["cestina", "CESTINA", "Čeština", "ceSTIna"].map(
      (query) => filterPickerOptions(ENDONYMS, query).map((option) => option.label),
    );
    for (const hit of cestinaHits) {
      expect(hit).toEqual(["Čeština"]);
    }
    expect(
      filterPickerOptions(ENDONYMS, "slovencina").map((option) => option.label),
    ).toEqual(["Slovenčina"]);
    expect(filterPickerOptions(ENDONYMS, "").map((option) => option.label)).toEqual(
      labels,
    );
    expect(filterPickerOptions(ENDONYMS, "xyz")).toEqual([]);
  });
});

describe("AC-PICKER-FILTER filterPickerOptions", () => {
  it("returns the expected subsets over the twelve endonyms", () => {
    expect(filterPickerOptions(ENDONYMS, "polski").map((o) => o.value)).toEqual([
      "pl",
    ]);
    expect(filterPickerOptions(ENDONYMS, "eng").map((o) => o.value)).toEqual([
      "en",
    ]);
    // Over twelve label shapes, a bare "c" also reaches Deutsch. That widening is the point of
    // covering the shipped set rather than four of it.
    expect(filterPickerOptions(ENDONYMS, "c").map((o) => o.value)).toEqual([
      "sk",
      "cs",
      "de",
    ]);
    expect(filterPickerOptions(ENDONYMS, "").map((o) => o.value)).toEqual([
      "en",
      "sk",
      "cs",
      "pl",
      "de",
      "pt",
      "is",
      "it",
      "nl",
      "da",
      "sv",
      "af",
    ]);
  });
});

describe("AC-PICKER-NAV nextPickerHighlight", () => {
  const mixed: readonly PremiumPickerOption[] = [
    { value: "a", label: "Alpha" },
    { value: "b", label: "Bravo", disabled: true },
    { value: "c", label: "Charlie" },
    { value: "d", label: "Delta", disabled: true },
    { value: "e", label: "Echo" },
  ];

  it("skips disabled options, wraps at both ends, and Home/End land on enabled extremes", () => {
    expect(nextPickerHighlight(mixed, -1, "ArrowDown")).toBe(0);
    expect(nextPickerHighlight(mixed, 0, "ArrowDown")).toBe(2);
    expect(nextPickerHighlight(mixed, 2, "ArrowDown")).toBe(4);
    expect(nextPickerHighlight(mixed, 4, "ArrowDown")).toBe(0);
    expect(nextPickerHighlight(mixed, 1, "ArrowDown")).toBe(2);

    expect(nextPickerHighlight(mixed, -1, "ArrowUp")).toBe(4);
    expect(nextPickerHighlight(mixed, 0, "ArrowUp")).toBe(4);
    expect(nextPickerHighlight(mixed, 4, "ArrowUp")).toBe(2);
    expect(nextPickerHighlight(mixed, 2, "ArrowUp")).toBe(0);
    expect(nextPickerHighlight(mixed, 3, "ArrowUp")).toBe(2);

    expect(nextPickerHighlight(mixed, 2, "Home")).toBe(0);
    expect(nextPickerHighlight(mixed, 2, "End")).toBe(4);
    expect(nextPickerHighlight(mixed, -1, "Home")).toBe(0);
    expect(nextPickerHighlight(mixed, -1, "End")).toBe(4);
  });

  it("returns -1 when every option is disabled", () => {
    const none: readonly PremiumPickerOption[] = [
      { value: "x", label: "X", disabled: true },
      { value: "y", label: "Y", disabled: true },
    ];
    expect(nextPickerHighlight(none, -1, "ArrowDown")).toBe(-1);
    expect(nextPickerHighlight(none, 0, "ArrowUp")).toBe(-1);
    expect(nextPickerHighlight(none, 1, "Home")).toBe(-1);
    expect(nextPickerHighlight(none, 1, "End")).toBe(-1);
  });
});

function pickerMarkup(value: string): string {
  return renderToStaticMarkup(
    createElement(PremiumPicker, {
      id: "endonym-picker",
      options: ENDONYMS,
      value,
      onChange: () => undefined,
      searchPlaceholder: "Search",
      emptyText: "No match",
      ariaLabel: "Interface language",
    }),
  );
}

function mixedMarkup(value: string): string {
  return renderToStaticMarkup(
    createElement(PremiumPicker, {
      id: "mixed-picker",
      options: MIXED_FLAGS,
      value,
      onChange: () => undefined,
      searchPlaceholder: "Search",
      emptyText: "No match",
      ariaLabel: "Mixed flags",
    }),
  );
}

function rowMarkup(markup: string, value: string): string {
  const start = markup.indexOf(`data-option-value="${value}"`);
  expect(start).toBeGreaterThan(-1);
  return markup.slice(start, markup.indexOf("</li>", start));
}

describe("AC-PICKER-FLAGLESS rows without a flag", () => {
  it("renders a flag on every shipped row and the trigger image too", () => {
    const markup = pickerMarkup("de");
    for (const option of ENDONYMS) {
      const row = rowMarkup(markup, option.value);
      expect(row).toContain(option.label);
      expect(row).toContain(`src="${option.flagSrc}"`);
    }
    // Twelve rows plus the closed trigger, which repeats the selected row's flag.
    expect(markup.match(/<img/g)?.length ?? 0).toBe(13);
  });

  it("renders a label and NO image for a row that has no flag", () => {
    const markup = mixedMarkup("en");
    expect(rowMarkup(markup, "xx")).toContain("Ruritanian");
    expect(rowMarkup(markup, "xx")).not.toContain("<img");
    expect(rowMarkup(markup, "en")).toContain('src="/en.png"');
    // Two flagged rows plus the trigger; the flagless row contributes nothing.
    expect(markup.match(/<img/g)?.length ?? 0).toBe(3);
  });

  it("omits the trigger image when the SELECTED row has no flag", () => {
    const markup = mixedMarkup("xx");
    expect(markup.match(/<img/g)?.length ?? 0).toBe(2);
  });
});
