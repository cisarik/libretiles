import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CompletionSourceBadge } from "./CompletionSourceBadge";

describe("CompletionSourceBadge", () => {
  it.each([
    ["provider_candidate", "Provider candidate"], ["backend_ranked_candidate", "Backend ranked candidate"],
    ["repair_candidate", "Repair candidate"], ["backend_witness_rescue", "Backend legal rescue"],
    ["genuine_no_move_exchange", "No legal move: exchange"], ["genuine_no_move_pass", "No legal move: pass"],
    ["unexpected", "Unknown source"],
  ])("labels %s", (source, label) => {
    expect(renderToStaticMarkup(createElement(CompletionSourceBadge, { source }))).toContain(label);
  });
});
