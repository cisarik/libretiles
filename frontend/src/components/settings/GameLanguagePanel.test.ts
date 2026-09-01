import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";

import { GameLanguagePanel } from "./GameLanguagePanel";
import { useGameStore } from "@/hooks/useGameStore";
import type { VariantSummary } from "@/lib/types";

const playable: VariantSummary = {
  slug: "czech",
  display_name: "Czech",
  language_code: "cs",
  readiness: "playable",
};
const unavailable: VariantSummary = {
  slug: "ghost",
  display_name: "Ghost",
  language_code: "xx",
  readiness: "unavailable",
};

function renderPanel(variants: VariantSummary[], selected = "english") {
  return renderToStaticMarkup(
    createElement(GameLanguagePanel, {
      variants,
      selected,
      onSelect: () => {},
    }),
  );
}

describe("GameLanguagePanel", () => {
  beforeEach(() => {
    useGameStore.setState(useGameStore.getInitialState(), true);
  });

  it("renders an unavailable variant as disabled", () => {
    const markup = renderPanel([playable, unavailable], "czech");
    expect(markup).toContain('data-variant-slug="ghost"');
    expect(markup).toContain('data-variant-readiness="unavailable"');
    const ghostStart = markup.lastIndexOf("<", markup.indexOf('data-variant-slug="ghost"'));
    const ghostEnd = markup.indexOf(">", markup.indexOf('data-variant-slug="ghost"'));
    const ghostTag = markup.slice(ghostStart, ghostEnd + 1);
    expect(ghostTag).toContain('aria-disabled="true"');
    expect(ghostTag.replace('aria-disabled="true"', "")).toMatch(/\bdisabled\b/);
    const czechStart = markup.lastIndexOf("<", markup.indexOf('data-variant-slug="czech"'));
    const czechEnd = markup.indexOf(">", markup.indexOf('data-variant-slug="czech"'));
    const czechTag = markup.slice(czechStart, czechEnd + 1);
    expect(czechTag).toContain('aria-disabled="false"');
    expect(czechTag.replace('aria-disabled="false"', "")).not.toMatch(/\bdisabled\b/);
  });
});
