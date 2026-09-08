import { describe, expect, it } from "vitest";
import { adminReplayFixture } from "./admin-replay.fixtures";
import { hasRecordedBingo, inspectMoveWords, scoreEquation } from "./admin-move-inspection";

describe("admin move inspection", () => {
  it("formats backend-recorded tile and word premium math", () => {
    const move = adminReplayFixture().plies[0];
    expect(scoreEquation(move.words_formed[0])).toBe("[A(1) + T(1)] × 2 DW = 4");
    expect(inspectMoveWords(move)[0]).toMatchObject({ label: "Formed word", reconciles: true });
  });

  it("recognizes bingo only when the stored total reconciles", () => {
    const move = adminReplayFixture().plies[0];
    move.placements = Array.from({ length: 7 }, (_, col) => ({ row: 7, col, letter: "A" }));
    move.points = move.words_formed[0].score + 50;
    expect(hasRecordedBingo(move)).toBe(true);
    move.points += 1;
    expect(hasRecordedBingo(move)).toBe(false);
  });
});
