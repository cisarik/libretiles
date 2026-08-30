import { describe, expect, it } from "vitest";
import { liveOptInEnabled } from "./ai-play-diagnostic";

describe("ai-play-diagnostic live worker", () => {
  it("exits before runtime resolution without the sentinel", () => {
    expect(liveOptInEnabled()).toBe(false);
    expect(process.env.LIBRETILES_AI_PLAY_LIVE).not.toBe("1");
  });
});
