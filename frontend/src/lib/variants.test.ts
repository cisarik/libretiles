import { describe, expect, it } from "vitest";
import type { VariantSummary } from "@/lib/types";
import {
  isSyntacticallyValidSlug,
  reconcileSelectedVariantSlug,
} from "./variants";

const english: VariantSummary = {
  slug: "english",
  display_name: "English",
  language_code: "en",
  readiness: "playable",
};
const czech: VariantSummary = {
  slug: "czech",
  display_name: "Czech",
  language_code: "cs",
  readiness: "playable",
};
const ghost: VariantSummary = {
  slug: "ghost",
  display_name: "Ghost",
  language_code: "xx",
  readiness: "unavailable",
};

describe("reconcileSelectedVariantSlug", () => {
  it("keeps a playable current slug", () => {
    expect(reconcileSelectedVariantSlug("czech", [english, czech, ghost])).toBe(
      "czech",
    );
  });

  it("reconciles an absent slug to the first playable row", () => {
    expect(reconcileSelectedVariantSlug("hungarian", [english, czech, ghost])).toBe(
      "english",
    );
  });

  it("reconciles an unavailable slug to the first playable row", () => {
    expect(reconcileSelectedVariantSlug("ghost", [english, czech, ghost])).toBe(
      "english",
    );
  });

  it("returns null when no playable row exists", () => {
    expect(reconcileSelectedVariantSlug("english", [ghost])).toBeNull();
    expect(reconcileSelectedVariantSlug("english", [])).toBeNull();
  });
});

describe("isSyntacticallyValidSlug", () => {
  it("accepts lowercase hyphenated slugs and rejects the rest", () => {
    expect(isSyntacticallyValidSlug("czech")).toBe(true);
    expect(isSyntacticallyValidSlug("foo-bar")).toBe(true);
    expect(isSyntacticallyValidSlug("")).toBe(false);
    expect(isSyntacticallyValidSlug("Foo")).toBe(false);
    expect(isSyntacticallyValidSlug("a b")).toBe(false);
  });
});
