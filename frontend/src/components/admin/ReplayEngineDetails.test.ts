import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { ReplayEngineDetails } from "./ReplayEngineDetails";
import type { AdminDiagnosticPly } from "@/lib/types";

it("renders no-run and preserves null, false, and zero meanings", () => {
  expect(renderToStaticMarkup(createElement(ReplayEngineDetails, { diagnostic: null }))).toContain("No diagnostic run linked to this move");
  const diagnostic = { model_authored: false, first_validate_valid: null, valid_candidate_count: 0, model_legal_score: 0, ranked_best_score: null, ranked_search_complete: false, playability_status: "found", assist_mode: "assisted", score_authority: "engine", executed_runtime_mode: "fake", terminal_cause: null, wall_clock_ms: 0 } as AdminDiagnosticPly;
  const markup = renderToStaticMarkup(createElement(ReplayEngineDetails, { diagnostic }));
  expect(markup).toContain("No"); expect(markup).toContain("Not measured"); expect(markup).toContain(">0<"); expect(markup).toContain("fake");
});
