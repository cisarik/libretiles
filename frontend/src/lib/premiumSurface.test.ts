import { describe, expect, it } from "vitest";
import {
  PREMIUM_PING_PONG_TILE_STYLE,
  isAttemptPingPongActive,
  pingPongTileMotion,
} from "./premiumSurface";

describe("pingPongTileMotion", () => {
  it("animates immediately with a mirrored repeat and zero delay", () => {
    const motion = pingPongTileMotion(false);
    expect(motion).not.toBeNull();
    expect(motion?.transition.delay).toBe(0);
    expect(motion?.transition.repeat).toBe(Infinity);
    expect(motion?.transition.repeatType).toBe("reverse");
    expect(motion?.x).toEqual([-3, 3]);
  });

  it("returns null under reduced motion so callers render a static tile", () => {
    expect(pingPongTileMotion(true)).toBeNull();
  });
});

describe("isAttemptPingPongActive", () => {
  it("binds the ping-pong strictly to the attempt lifecycle", () => {
    expect(isAttemptPingPongActive("pending", true)).toBe(true);
    expect(isAttemptPingPongActive("active", true)).toBe(true);
    expect(isAttemptPingPongActive("pending", false)).toBe(false);
    // A failed attempt never animates even if the index still points at it.
    expect(isAttemptPingPongActive("failed", true)).toBe(false);
  });
});

describe("PREMIUM_PING_PONG_TILE_STYLE", () => {
  it("uses gold/black chrome", () => {
    const background = PREMIUM_PING_PONG_TILE_STYLE.backgroundImage ?? "";
    expect(background).toContain("254,240,138"); // light gold
    expect(background).toContain("251,191,36"); // amber gold
    expect(background.toLowerCase()).toContain("rgba(66,32,6"); // deep black-brown
  });
});
