import { describe, expect, it } from "vitest";

import { foldForSearch } from "@/lib/i18n/locales";

import {
  filterPickerOptions,
  nextPickerHighlight,
  type PremiumPickerOption,
} from "./PremiumPicker";

const ENDONYMS: readonly PremiumPickerOption[] = [
  { value: "en", label: "English", flagSrc: "/en.png" },
  { value: "sk", label: "Slovenčina", flagSrc: "/sk.png" },
  { value: "cs", label: "Čeština", flagSrc: "/cs.png" },
  { value: "pl", label: "Polski", flagSrc: "/pl.png" },
];

describe("AC-FOLD foldForSearch", () => {
  it("folds every diacritic these four locales use, including stroke letters NFD cannot fold", () => {
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
  it("returns the expected subsets over the four endonyms", () => {
    expect(filterPickerOptions(ENDONYMS, "polski").map((o) => o.value)).toEqual([
      "pl",
    ]);
    expect(filterPickerOptions(ENDONYMS, "eng").map((o) => o.value)).toEqual([
      "en",
    ]);
    expect(filterPickerOptions(ENDONYMS, "c").map((o) => o.value)).toEqual([
      "sk",
      "cs",
    ]);
    expect(filterPickerOptions(ENDONYMS, "").map((o) => o.value)).toEqual([
      "en",
      "sk",
      "cs",
      "pl",
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
