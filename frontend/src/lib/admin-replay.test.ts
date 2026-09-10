import { describe, expect, it } from "vitest";
import { adminReplayFixture } from "./admin-replay.fixtures";
import { buildReplayFrames, parseAdminReplay } from "./admin-replay";

describe("admin replay ingress and reconstruction", () => {
  it("validates and reconstructs atomic blank tiles without mutating prior frames", () => {
    const payload = parseAdminReplay(adminReplayFixture());
    const frames = buildReplayFrames(payload);
    expect(frames).toHaveLength(3);
    expect(frames[0].board?.[7][7]).toBeNull();
    expect(frames[1].board?.[7][7]).toEqual({ token: "A", blank_as: null });
    expect(frames[1].board?.[7][8]).toEqual({ token: "T", blank_as: null });
    expect(frames[2].board).toBe(frames[1].board);
    expect(frames[1].board?.[6]).toBe(frames[0].board?.[6]);
  });

  it("rejects schema drift, malformed blanks, and non-increasing sequences", () => {
    expect(() => parseAdminReplay({ ...adminReplayFixture(), replay_schema_version: 2 })).toThrow();
    const malformed = adminReplayFixture(); malformed.plies[0].board_delta[0].token = "?";
    expect(() => parseAdminReplay(malformed)).toThrow();
    const unordered = adminReplayFixture(); unordered.plies[1].seq = 1;
    expect(() => parseAdminReplay(unordered)).toThrow();
  });

  it("preserves unavailable partial history", () => {
    const payload = adminReplayFixture(); payload.initial_state.initial_board = null; payload.replay_status = "partial";
    expect(buildReplayFrames(parseAdminReplay(payload))[0].board).toBeNull();
  });
});
