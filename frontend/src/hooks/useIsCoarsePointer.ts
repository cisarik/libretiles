"use client";

import { useSyncExternalStore } from "react";

function getCoarsePointerSnapshot() {
  if (typeof window === "undefined") return false;

  return (
    window.matchMedia("(pointer: coarse)").matches ||
    navigator.maxTouchPoints > 0
  );
}

function subscribeToCoarsePointer(callback: () => void) {
  if (typeof window === "undefined") {
    return () => {};
  }

  const mediaQuery = window.matchMedia("(pointer: coarse)");
  const handleChange = () => callback();

  mediaQuery.addEventListener("change", handleChange);
  window.addEventListener("resize", handleChange, { passive: true });

  return () => {
    mediaQuery.removeEventListener("change", handleChange);
    window.removeEventListener("resize", handleChange);
  };
}

export function useIsCoarsePointer() {
  return useSyncExternalStore(
    subscribeToCoarsePointer,
    getCoarsePointerSnapshot,
    () => false,
  );
}
