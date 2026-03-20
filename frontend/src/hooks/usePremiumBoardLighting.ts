"use client";

import { RefObject, useEffect } from "react";

type DeviceOrientationPermissionState = "granted" | "denied";
type DeviceOrientationWithPermission = typeof DeviceOrientationEvent & {
  requestPermission?: () => Promise<DeviceOrientationPermissionState>;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function lerp(start: number, end: number, amount: number) {
  return start + (end - start) * amount;
}

function getOrientationAngle() {
  if (typeof window === "undefined") return 0;

  if (typeof window.screen?.orientation?.angle === "number") {
    return window.screen.orientation.angle;
  }

  const legacyOrientation = window as Window & { orientation?: number };
  return typeof legacyOrientation.orientation === "number"
    ? legacyOrientation.orientation
    : 0;
}

function mapOrientationDelta(deltaBeta: number, deltaGamma: number) {
  const angle = ((getOrientationAngle() % 360) + 360) % 360;

  switch (angle) {
    case 90:
      return {
        x: clamp(deltaBeta / 24, -1, 1),
        y: clamp(-deltaGamma / 22, -1, 1),
      };
    case 180:
      return {
        x: clamp(-deltaGamma / 22, -1, 1),
        y: clamp(-deltaBeta / 24, -1, 1),
      };
    case 270:
      return {
        x: clamp(-deltaBeta / 24, -1, 1),
        y: clamp(deltaGamma / 22, -1, 1),
      };
    default:
      return {
        x: clamp(deltaGamma / 22, -1, 1),
        y: clamp(deltaBeta / 24, -1, 1),
      };
  }
}

export function usePremiumBoardLighting(
  ref: RefObject<HTMLDivElement | null>,
  disabled = false,
) {
  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const reduceMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

    let currentX = 0;
    let currentY = 0;
    let targetX = 0;
    let targetY = 0;
    let frameId: number | null = null;
    let orientationEnabled = false;
    let orientationPermissionAttempted = false;
    let baseBeta: number | null = null;
    let baseGamma: number | null = null;
    let lastPointerInputAt = 0;
    const styleCache = new Map<string, string>();

    const setStyle = (name: string, value: string) => {
      if (styleCache.get(name) === value) return;
      styleCache.set(name, value);
      element.style.setProperty(name, value);
    };

    const applyLighting = (x: number, y: number) => {
      const intensity = Math.min(1, Math.hypot(x, y));

      setStyle("--board-light-x", `${(50 + x * 24).toFixed(2)}%`);
      setStyle("--board-light-y", `${(50 + y * 24).toFixed(2)}%`);
      setStyle("--board-sheen-angle", `${(140 + x * 22 - y * 14).toFixed(2)}deg`);
      setStyle("--board-glow-strength", `${(0.34 + intensity * 0.22).toFixed(3)}`);
      setStyle("--board-shadow-x", `${(-x * 10).toFixed(2)}px`);
      setStyle("--board-shadow-y", `${(18 - y * 6).toFixed(2)}px`);
      setStyle("--board-ambient-x", `${(x * 10).toFixed(2)}px`);
      setStyle("--board-ambient-y", `${(y * 10).toFixed(2)}px`);
      setStyle("--board-light-core-size", `${(42 + intensity * 6).toFixed(2)}%`);
      setStyle("--board-light-field-size", `${(78 + intensity * 10).toFixed(2)}%`);
      setStyle("--board-premium-field-size", `${(70 + intensity * 8).toFixed(2)}%`);
    };

    const cancelAnimation = () => {
      if (frameId !== null) {
        cancelAnimationFrame(frameId);
        frameId = null;
      }
    };

    const animate = () => {
      const delta = Math.max(
        Math.abs(targetX - currentX),
        Math.abs(targetY - currentY),
      );
      const smoothing = clamp(0.34 + delta * 0.42, 0.34, 0.78);

      currentX = lerp(currentX, targetX, smoothing);
      currentY = lerp(currentY, targetY, smoothing);

      if (Math.abs(targetX - currentX) < 0.0015 && Math.abs(targetY - currentY) < 0.0015) {
        currentX = targetX;
        currentY = targetY;
        applyLighting(currentX, currentY);
        frameId = null;
        return;
      }

      applyLighting(currentX, currentY);
      frameId = requestAnimationFrame(animate);
    };

    const scheduleAnimation = () => {
      if (frameId !== null) return;
      frameId = requestAnimationFrame(animate);
    };

    const setTarget = (x: number, y: number) => {
      targetX = clamp(x, -1.18, 1.18);
      targetY = clamp(y, -1.18, 1.18);
      scheduleAnimation();
    };

    const updateFromClientPoint = (clientX: number, clientY: number) => {
      const rect = element.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;

      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const boardX = (clientX - centerX) / (rect.width * 0.48);
      const boardY = (clientY - centerY) / (rect.height * 0.48);
      const viewportX = (clientX / Math.max(window.innerWidth, 1) - 0.5) * 2;
      const viewportY = (clientY / Math.max(window.innerHeight, 1) - 0.5) * 2;

      const normalizedX = clamp(boardX * 0.78 + viewportX * 0.36, -1.15, 1.15);
      const normalizedY = clamp(boardY * 0.78 + viewportY * 0.36, -1.15, 1.15);

      setTarget(normalizedX, normalizedY);
    };

    const handleDeviceOrientation = (event: DeviceOrientationEvent) => {
      if (reduceMotionQuery.matches) return;
      if (event.beta == null || event.gamma == null) return;

      if (baseBeta == null || baseGamma == null) {
        baseBeta = event.beta;
        baseGamma = event.gamma;
        return;
      }

      const { x, y } = mapOrientationDelta(
        event.beta - baseBeta,
        event.gamma - baseGamma,
      );

      setTarget(x * 0.98, y * 0.98);
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (reduceMotionQuery.matches) return;

      if (event.pointerType === "mouse" || !orientationEnabled) {
        lastPointerInputAt = performance.now();
        updateFromClientPoint(event.clientX, event.clientY);
      }
    };

    const handleTouchEnd = (event: PointerEvent) => {
      if (reduceMotionQuery.matches) return;
      if (event.pointerType === "mouse" || orientationEnabled) return;
      setTarget(0, 0);
    };

    const handleWindowBlur = () => {
      if (reduceMotionQuery.matches || orientationEnabled) return;
      if (performance.now() - lastPointerInputAt < 120) return;
      setTarget(0, 0);
    };

    const resetOrientationBase = () => {
      baseBeta = null;
      baseGamma = null;
    };

    const enableOrientation = async (fromGesture: boolean) => {
      if (orientationEnabled) return;
      if (!("DeviceOrientationEvent" in window)) return;

      const OrientationEvent =
        window.DeviceOrientationEvent as DeviceOrientationWithPermission;

      if (typeof OrientationEvent.requestPermission === "function") {
        if (!fromGesture || orientationPermissionAttempted) return;

        orientationPermissionAttempted = true;

        try {
          const permission = await OrientationEvent.requestPermission();
          if (permission !== "granted") return;
        } catch {
          return;
        }
      }

      window.addEventListener("deviceorientation", handleDeviceOrientation, {
        passive: true,
      });
      orientationEnabled = true;
      resetOrientationBase();
    };

    const handleFirstGesture = () => {
      void enableOrientation(true);
    };

    const handleReduceMotionChange = (event: MediaQueryListEvent) => {
      if (event.matches) {
        cancelAnimation();
        targetX = 0;
        targetY = 0;
        currentX = 0;
        currentY = 0;
        applyLighting(0, 0);
        return;
      }

      void enableOrientation(false);
    };

    applyLighting(0, 0);

    if (disabled) {
      return () => {
        cancelAnimation();
      };
    }

    if (!reduceMotionQuery.matches) {
      element.addEventListener("pointerdown", handleFirstGesture, { passive: true });
      window.addEventListener("pointermove", handlePointerMove, { passive: true });
      window.addEventListener("pointerdown", handlePointerMove, { passive: true });
      window.addEventListener("pointerup", handleTouchEnd, { passive: true });
      window.addEventListener("pointercancel", handleTouchEnd, { passive: true });
      window.addEventListener("blur", handleWindowBlur);
      window.addEventListener("orientationchange", resetOrientationBase, {
        passive: true,
      });
      reduceMotionQuery.addEventListener("change", handleReduceMotionChange);
      void enableOrientation(false);
    }

    return () => {
      cancelAnimation();
      reduceMotionQuery.removeEventListener("change", handleReduceMotionChange);
      element.removeEventListener("pointerdown", handleFirstGesture);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerdown", handlePointerMove);
      window.removeEventListener("pointerup", handleTouchEnd);
      window.removeEventListener("pointercancel", handleTouchEnd);
      window.removeEventListener("blur", handleWindowBlur);
      window.removeEventListener("orientationchange", resetOrientationBase);

      if (orientationEnabled) {
        window.removeEventListener("deviceorientation", handleDeviceOrientation);
      }
    };
  }, [disabled, ref]);
}
