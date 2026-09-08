import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { adminReplayFixture } from "@/lib/admin-replay.fixtures";
import { ReplayScoreBreakdown } from "./ReplayScoreBreakdown";

it("renders exact score math and authority evidence", () => {
  const markup = renderToStaticMarkup(createElement(ReplayScoreBreakdown, { move: adminReplayFixture().plies[0] }));
  expect(markup).toContain("[A(1) + T(1)] × 2 DW = 4");
  expect(markup).toContain("Backend certified:");
  expect(markup).toContain("Collins Scrabble Words (2019)");
});

it("labels legacy score records", () => {
  const move = adminReplayFixture().plies[0]; delete move.words_formed[0].inspection;
  const markup = renderToStaticMarkup(createElement(ReplayScoreBreakdown, { move }));
  expect(markup).toContain("Per-tile breakdown was not recorded.");
});

it("renders the AI judge inspection trigger for judged moves", () => {
  const move = adminReplayFixture().plies[0];
  move.ai_metadata.judge_mode = "ai";
  const markup = renderToStaticMarkup(createElement(ReplayScoreBreakdown, { move }));
  expect(markup).toContain("⚖️ AI Judge verdict");
});
