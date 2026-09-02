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

function optionTag(markup: string, slug: string): string {
  const marker = `data-option-value="${slug}"`;
  const start = markup.lastIndexOf("<", markup.indexOf(marker));
  const end = markup.indexOf(">", markup.indexOf(marker));
  return markup.slice(start, end + 1);
}

describe("GameLanguagePanel", () => {
  beforeEach(() => {
    useGameStore.setState(useGameStore.getInitialState(), true);
  });

  it("renders an unavailable variant as disabled", () => {
    const markup = renderPanel([playable, unavailable], "czech");
    expect(markup).toContain('data-option-value="ghost"');
    expect(markup).toContain('data-option-value="czech"');
    const ghostTag = optionTag(markup, "ghost");
    expect(ghostTag).toContain('aria-disabled="true"');
    expect(ghostTag.replace('aria-disabled="true"', "")).not.toMatch(
      /\bdisabled\b/,
    );
    const czechTag = optionTag(markup, "czech");
    expect(czechTag).toContain('aria-disabled="false"');
    expect(czechTag.replace('aria-disabled="false"', "")).not.toMatch(
      /\bdisabled\b/,
    );
  });

  it("falls back to display_name for an unknown slug", () => {
    const markup = renderPanel([playable, unavailable], "czech");
    expect(markup).toContain("Ghost");
    expect(markup).toContain("Czech");
  });
});
