import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { ReplayBoard } from "./ReplayBoard";
import { emptyAdminBoard } from "@/lib/admin-replay.fixtures";

it("labels and highlights exactly the placed replay tile", () => {
  const board = emptyAdminBoard(); board[7][7] = { token: "?", blank_as: "SZ" };
  const markup = renderToStaticMarkup(createElement(ReplayBoard, { board, highlighted: [{ row: 7, col: 7, token: "?", blank_as: "SZ" }], tilePoints: { SZ: 4, "?": 0 }, frameKey: 1 }));
  expect(markup).toContain("SZ, 0 points, blank, placed this ply"); expect(markup).toContain("highlight");
});

it("accepts a live simulation accessibility label", () => {
  const markup = renderToStaticMarkup(createElement(ReplayBoard, { board: emptyAdminBoard(), highlighted: [], tilePoints: {}, ariaLabel: "Live simulation board" }));
  expect(markup).toContain('aria-label="Live simulation board"');
});
