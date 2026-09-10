import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { ReplayControls } from "./ReplayControls";
import { adminReplayFixture } from "@/lib/admin-replay.fixtures";

it("renders VCR controls, slider, speeds, and move ticker", () => {
  const data = adminReplayFixture(); const markup = renderToStaticMarkup(createElement(ReplayControls, { currentPlyIndex: 1, totalPlies: 2, isPlaying: false, playbackSpeed: 1, move: data.plies[0], players: data.players, onFirst() {}, onBack() {}, onToggle() {}, onForward() {}, onLast() {}, onSeek() {}, onPause() {}, onSpeed() {} }));
  expect(markup).toContain("Replay timeline"); expect(markup).toContain("0.5x"); expect(markup).toContain("Ply 1 of 2: Ada played AT for 4 points"); expect(markup).toContain('aria-label="Step backward"');
});
