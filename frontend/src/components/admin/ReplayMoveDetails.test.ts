import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { ReplayMoveDetails } from "./ReplayMoveDetails";
import { adminReplayFixture } from "@/lib/admin-replay.fixtures";

it("renders stored word score, multiplier, and coordinates", () => {
  const data = adminReplayFixture(); const markup = renderToStaticMarkup(createElement(ReplayMoveDetails, { move: data.plies[0], players: data.players, previousScores: [0, 0] }));
  expect(markup).toContain("Stored sequence 1"); expect(markup).toContain("SZ · 12 points"); expect(markup).toContain("Word multiplier: 2"); expect(markup).toContain("8,8");
});
