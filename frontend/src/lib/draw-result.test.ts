import { describe, expect, it } from "vitest";
import { describeDrawReason } from "./draw-result";

describe("describeDrawReason", () => {
  it("names the winning letter in both locales", () => {
    expect(describeDrawReason("en", "B", "K", true)).toBe(
      "B is closer to A than K.",
    );
    expect(describeDrawReason("sk", "B", "K", true)).toBe(
      "B je bližšie k A ako K.",
    );
  });

  it("names the AI's letter as the winner when the AI starts", () => {
    expect(describeDrawReason("en", "K", "B", false)).toBe(
      "B is closer to A than K.",
    );
    expect(describeDrawReason("sk", "K", "B", false)).toBe(
      "B je bližšie k A ako K.",
    );
  });

  it("says whose blank won, not just that a blank appeared", () => {
    expect(describeDrawReason("sk", "?", "K", true)).toBe(
      "Tvoj žolík vyhráva ťah o poradie.",
    );
    expect(describeDrawReason("sk", "K", "?", false)).toBe(
      "Žolíka vytiahlo AI.",
    );
    expect(describeDrawReason("en", "?", "K", true)).toBe(
      "Your blank wins the draw.",
    );
    expect(describeDrawReason("en", "K", "?", false)).toBe(
      "The AI drew the blank.",
    );
  });

  it("handles two blanks, which the backend resolves in the human's favour", () => {
    // backend/game/services.py maps a blank to "" before comparing, so
    // "" <= "" is true and slot 0 starts.
    expect(describeDrawReason("en", "?", "?", true)).toBe(
      "Both tiles are blanks, so you start.",
    );
    expect(describeDrawReason("sk", "?", "?", true)).toBe(
      "Obidve písmená sú žolíky, takže začínaš ty.",
    );
  });

  it("never renders the raw '?' placeholder to the user", () => {
    for (const locale of ["en", "sk"] as const) {
      for (const [h, a, first] of [
        ["?", "K", true],
        ["K", "?", false],
        ["?", "?", true],
      ] as const) {
        expect(describeDrawReason(locale, h, a, first)).not.toContain("?");
      }
    }
  });
});
