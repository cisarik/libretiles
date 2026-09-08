import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { adminReplayFixture } from "@/lib/admin-replay.fixtures";
import { ReplayToolTimeline } from "./ReplayToolTimeline";

it("renders chronological tool calls and telemetry chips", () => {
  const markup = renderToStaticMarkup(createElement(ReplayToolTimeline, { move: adminReplayFixture().plies[0] }));
  expect(markup).toContain("Provider candidate"); expect(markup).toContain("Attempt 1");
  expect(markup).toContain("validateMove"); expect(markup).toContain("Valid"); expect(markup).toContain("finishMove");
  expect(markup).toContain("Time to submission: 210 ms");
});

it("shows the legacy trace fallback", () => {
  const move = adminReplayFixture().plies[0]; move.ai_metadata = {};
  expect(renderToStaticMarkup(createElement(ReplayToolTimeline, { move }))).toContain("Tool-call history was not recorded.");
});
