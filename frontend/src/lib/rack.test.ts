import { describe, expect, it } from "vitest";
import { isPlausibleRack } from "./rack";

const ENGLISH = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

const SLOVAK = [
  "A", "Á", "Ä", "B", "C", "Č", "D", "Ď", "E", "É", "F", "G", "H", "I", "Í",
  "J", "K", "L", "Ĺ", "Ľ", "M", "N", "Ň", "O", "Ó", "Ô", "P", "R", "Ŕ", "S",
  "Š", "T", "Ť", "U", "Ú", "V", "X", "Y", "Ý", "Z", "Ž",
];

describe("isPlausibleRack", () => {
  it("accepts a Slovak rack with Á when the session alphabet is provided", () => {
    expect(isPlausibleRack(["Á", "U", "T", "O"], SLOVAK)).toBe(true);
  });

  it("rejects emoji with or without an alphabet", () => {
    expect(isPlausibleRack(["😀", "A"], SLOVAK)).toBe(false);
    expect(isPlausibleRack(["😀"])).toBe(false);
  });

  it("rejects Á when the session alphabet is English A–Z", () => {
    expect(isPlausibleRack(["Á"], ENGLISH)).toBe(false);
  });

  it("accepts Á via Unicode fallback when alphabet is missing", () => {
    expect(isPlausibleRack(["Á", "U", "T", "O"])).toBe(true);
  });

  it("allows at most two blanks and one to seven tiles", () => {
    expect(isPlausibleRack(["?", "?", "A"], SLOVAK)).toBe(true);
    expect(isPlausibleRack(["?", "?", "?", "A"], SLOVAK)).toBe(false);
    expect(isPlausibleRack([])).toBe(false);
    expect(isPlausibleRack(["A", "B", "C", "D", "E", "F", "G", "H"], ENGLISH)).toBe(
      false,
    );
  });
});
