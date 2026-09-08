import { afterEach, describe, expect, it, vi } from "vitest";
import { ReplayEngineController } from "@/lib/admin-replay-engine";

afterEach(() => vi.useRealTimers());
describe("ReplayEngineController", () => {
  it.each([[0.5, 2000], [1, 1000], [2, 500]] as const)("advances at %sx after %sms", (speed, duration) => {
    vi.useFakeTimers(); const engine = new ReplayEngineController(2); engine.setSpeed(speed); engine.play();
    vi.advanceTimersByTime(duration - 1); expect(engine.getSnapshot().currentPlyIndex).toBe(0);
    vi.advanceTimersByTime(1); expect(engine.getSnapshot().currentPlyIndex).toBe(1); engine.dispose();
  });
  it("auto-pauses, clamps seeks, and restarts at the end", () => {
    vi.useFakeTimers(); const engine = new ReplayEngineController(1); engine.play(); vi.advanceTimersByTime(1000);
    expect(engine.getSnapshot()).toMatchObject({ currentPlyIndex: 1, isPlaying: false }); engine.play();
    expect(engine.getSnapshot()).toMatchObject({ currentPlyIndex: 0, isPlaying: true }); engine.goToPly(99);
    expect(engine.getSnapshot()).toMatchObject({ currentPlyIndex: 1, isPlaying: false }); engine.dispose();
  });
  it("cancels pending work on pause and refuses zero-ply playback", () => {
    vi.useFakeTimers(); const engine = new ReplayEngineController(2); engine.play(); engine.pause(); vi.runAllTimers();
    expect(engine.getSnapshot().currentPlyIndex).toBe(0); const empty = new ReplayEngineController(0); empty.play();
    expect(empty.getSnapshot().isPlaying).toBe(false);
  });
});
