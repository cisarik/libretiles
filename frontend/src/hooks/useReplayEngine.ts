"use client";

import { useEffect, useMemo, useSyncExternalStore, type KeyboardEvent } from "react";
import { ReplayEngineController, type ReplaySpeed } from "@/lib/admin-replay-engine";

export function useReplayEngine(totalPlies: number) {
  const controller = useMemo(() => new ReplayEngineController(totalPlies), [totalPlies]);
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  useEffect(() => () => controller.dispose(), [controller]);
  useEffect(() => {
    const hidden = () => { if (document.hidden) controller.pause(); };
    document.addEventListener("visibilitychange", hidden);
    return () => document.removeEventListener("visibilitychange", hidden);
  }, [controller]);
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const target = event.target as HTMLElement;
    if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || target.isContentEditable || /^(INPUT|SELECT|BUTTON|A|TEXTAREA)$/.test(target.tagName)) return;
    const actions: Record<string, () => void> = {
      " ": controller.togglePlay, ArrowLeft: controller.stepBackward, ArrowRight: controller.stepForward,
      Home: () => controller.goToPly(0), End: () => controller.goToPly(totalPlies),
    };
    if (actions[event.key]) { event.preventDefault(); actions[event.key](); }
  };
  return {
    ...state, totalPlies, atStart: state.currentPlyIndex === 0, atEnd: state.currentPlyIndex === totalPlies,
    play: controller.play, pause: controller.pause, togglePlay: controller.togglePlay,
    stepForward: controller.stepForward, stepBackward: controller.stepBackward, goToPly: controller.goToPly,
    setSpeed: (speed: ReplaySpeed) => controller.setSpeed(speed), onKeyDown,
  };
}
