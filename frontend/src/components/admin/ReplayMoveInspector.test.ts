import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { ReplayMoveInspector } from "./ReplayMoveInspector";
import { adminReplayFixture } from "@/lib/admin-replay.fixtures";

it("renders an accessible collapsed inspector trigger", () => {
  const markup = renderToStaticMarkup(createElement(ReplayMoveInspector, { move: adminReplayFixture().plies[0] }));
  expect(markup).toContain("Deep move inspector");
  expect(markup).toContain('aria-expanded="false"');
  expect(markup).toContain("Inspect stored sequence 1");
});
