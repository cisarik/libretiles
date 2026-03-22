"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BOARD_SIZE } from "@/lib/constants";
import { Cell } from "./Cell";
import { useGameStore } from "@/hooks/useGameStore";
import { useIsCoarsePointer } from "@/hooks/useIsCoarsePointer";
import { usePremiumBoardLighting } from "@/hooks/usePremiumBoardLighting";

interface BoardDragPreview {
  row: number;
  col: number;
}

interface BoardProps {
  dragPreview: BoardDragPreview | null;
  isDraggingTile: boolean;
  onPlaceTile?: (row: number, col: number) => void;
}

type TouchMode = "idle" | "pan" | "pinch";

type BoardPoint = {
  x: number;
  y: number;
};

type ZoomRuntimeState = {
  scale: number;
  x: number;
  y: number;
  mode: TouchMode;
  lastPoint: BoardPoint | null;
  lastMidpoint: BoardPoint | null;
  lastTime: number;
  velocityX: number;
  velocityY: number;
  pinchStartDistance: number;
  pinchStartScale: number;
  pinchAnchor: BoardPoint | null;
  travel: number;
};

const MIN_BOARD_SCALE = 1;
const MAX_BOARD_SCALE = 2.75;
const PAN_INERTIA_FRICTION = 0.92;
const PAN_INERTIA_MIN_SPEED = 0.02;
const PAN_START_THRESHOLD = 6;
const PAN_ACTIVATION_THRESHOLD = 4;
const TAP_SUPPRESSION_MS = 180;
const ZOOM_ANIMATION_MS = 220;
const ZOOM_HINT_TIMEOUT_MS = 4200;
const ZOOM_HINT_STORAGE_KEY = "libretiles-mobile-zoom-hint-v1";

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function getTouchPoint(touch: Touch, rect: DOMRect): BoardPoint {
  return {
    x: touch.clientX - rect.left,
    y: touch.clientY - rect.top,
  };
}

function getMidpoint(a: BoardPoint, b: BoardPoint): BoardPoint {
  return {
    x: (a.x + b.x) / 2,
    y: (a.y + b.y) / 2,
  };
}

function getDistance(a: BoardPoint, b: BoardPoint): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function formatMoveCostValue(chargedUsd?: string | null): string {
  const normalizedUsd = chargedUsd?.trim();
  if (normalizedUsd && /^\d+(?:\.\d+)?$/.test(normalizedUsd)) {
    const numericUsd = Number.parseFloat(normalizedUsd);
    if (Number.isFinite(numericUsd)) {
      return `$${numericUsd.toFixed(6).replace(/0+$/, "").replace(/\.$/, ".000")}`;
    }
  }

  return "$0.000000";
}

export function Board({
  dragPreview,
  isDraggingTile,
  onPlaceTile,
}: BoardProps) {
  const gameState = useGameStore((s) => s.gameState);
  const lastMoveResultBilling = useGameStore((s) => s.lastMoveResult?.billing);
  const pendingTiles = useGameStore((s) => s.pendingTiles);
  const removePendingTile = useGameStore((s) => s.removePendingTile);
  const boardTheme = useGameStore((s) => s.boardTheme);
  const boardShineEnabled = useGameStore((s) => s.boardShineEnabled);
  const isCoarsePointer = useIsCoarsePointer();
  const boardRef = useRef<HTMLDivElement | null>(null);
  const zoomLayerRef = useRef<HTMLDivElement | null>(null);
  const zoomTransitionTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const zoomActiveRef = useRef(false);
  const hintTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hintRevealFrameRef = useRef<number | null>(null);
  const zoomRuntimeRef = useRef<ZoomRuntimeState>({
    scale: MIN_BOARD_SCALE,
    x: 0,
    y: 0,
    mode: "idle",
    lastPoint: null,
    lastMidpoint: null,
    lastTime: 0,
    velocityX: 0,
    velocityY: 0,
    pinchStartDistance: 0,
    pinchStartScale: MIN_BOARD_SCALE,
    pinchAnchor: null,
    travel: 0,
  });
  const inertiaFrameRef = useRef<number | null>(null);
  const suppressTapUntilRef = useRef(0);
  const [revealedMoveKey, setRevealedMoveKey] = useState<string | null>(null);
  const [zoomActive, setZoomActive] = useState(false);
  const [showZoomHint, setShowZoomHint] = useState(false);

  usePremiumBoardLighting(boardRef, isDraggingTile || !boardShineEnabled || isCoarsePointer);

  const grid = gameState?.board ?? Array(BOARD_SIZE).fill(".".repeat(BOARD_SIZE));
  const blanks = new Set(
    (gameState?.blanks ?? []).map((b) => `${b.row}-${b.col}`),
  );
  const lastMoveCells = gameState?.last_move_cells ?? [];
  const lastMoveWords = gameState?.last_move_words ?? [];
  const primaryWordCoords = lastMoveWords[0]?.coords ?? lastMoveCells;
  const lastMoveSet = new Set(primaryWordCoords.map((cell) => `${cell.row}-${cell.col}`));
  const lastMoveBilling = gameState?.last_move_billing ?? lastMoveResultBilling ?? null;
  const pendingSet = new Map(
    pendingTiles.map((t) => [`${t.row}-${t.col}`, t]),
  );

  const lastMoveRows = primaryWordCoords.map((cell) => cell.row);
  const lastMoveCols = primaryWordCoords.map((cell) => cell.col);
  const hasLastMove = primaryWordCoords.length > 0;
  const minRow = hasLastMove ? Math.min(...lastMoveRows) : 0;
  const maxRow = hasLastMove ? Math.max(...lastMoveRows) : 0;
  const minCol = hasLastMove ? Math.min(...lastMoveCols) : 0;
  const maxCol = hasLastMove ? Math.max(...lastMoveCols) : 0;
  const popupCenterX = ((minCol + maxCol + 1) / 2 / BOARD_SIZE) * 100;
  const popupAbove = minRow > 1;
  const popupTop = popupAbove
    ? `calc(${(minRow / BOARD_SIZE) * 100}% - 12px)`
    : `calc(${((maxRow + 1) / BOARD_SIZE) * 100}% + 12px)`;
  const primaryWord = lastMoveWords[0]?.word ?? null;
  const lastMoveCostValue = formatMoveCostValue(lastMoveBilling?.charged_usd);
  const moveRevealKey = `${gameState?.move_count ?? 0}:${primaryWord ?? ""}`;
  const showLastMoveInfo = revealedMoveKey === moveRevealKey;

  const clampBoardOffset = useCallback((scale: number, x: number, y: number) => {
    const shell = boardRef.current;
    if (!shell) return { x, y };

    const maxOffsetX = Math.max(0, (shell.clientWidth * scale - shell.clientWidth) / 2);
    const maxOffsetY = Math.max(0, (shell.clientHeight * scale - shell.clientHeight) / 2);

    return {
      x: clamp(x, -maxOffsetX, maxOffsetX),
      y: clamp(y, -maxOffsetY, maxOffsetY),
    };
  }, []);

  const clearZoomTransition = useCallback(() => {
    if (zoomTransitionTimeoutRef.current != null) {
      clearTimeout(zoomTransitionTimeoutRef.current);
      zoomTransitionTimeoutRef.current = null;
    }

    if (zoomLayerRef.current) {
      zoomLayerRef.current.style.transition = "";
    }
  }, []);

  const applyBoardTransform = useCallback((scale: number, x: number, y: number) => {
    const shell = boardRef.current;
    const zoomLayer = zoomLayerRef.current;
    if (!shell || !zoomLayer) return;

    const clampedOffset = clampBoardOffset(scale, x, y);
    const nextScale = clamp(scale, MIN_BOARD_SCALE, MAX_BOARD_SCALE);
    const runtime = zoomRuntimeRef.current;

    runtime.scale = nextScale;
    runtime.x = clampedOffset.x;
    runtime.y = clampedOffset.y;

    zoomLayer.style.transform =
      `translate3d(${clampedOffset.x}px, ${clampedOffset.y}px, 0) scale(${nextScale})`;
    const isZoomed = nextScale > 1.01;
    shell.dataset.zoomActive = isZoomed ? "true" : "false";

    if (zoomActiveRef.current !== isZoomed) {
      zoomActiveRef.current = isZoomed;
      setZoomActive(isZoomed);
    }
  }, [clampBoardOffset]);

  const stopPanInertia = useCallback(() => {
    if (inertiaFrameRef.current != null) {
      cancelAnimationFrame(inertiaFrameRef.current);
      inertiaFrameRef.current = null;
    }
  }, []);

  const animateBoardTransform = useCallback((scale: number, x: number, y: number) => {
    const zoomLayer = zoomLayerRef.current;
    stopPanInertia();
    clearZoomTransition();

    if (!zoomLayer) {
      applyBoardTransform(scale, x, y);
      return;
    }

    zoomLayer.style.transition = `transform ${ZOOM_ANIMATION_MS}ms cubic-bezier(0.22, 1, 0.36, 1)`;
    applyBoardTransform(scale, x, y);

    zoomTransitionTimeoutRef.current = setTimeout(() => {
      if (zoomLayerRef.current) {
        zoomLayerRef.current.style.transition = "";
      }
      zoomTransitionTimeoutRef.current = null;
    }, ZOOM_ANIMATION_MS);
  }, [applyBoardTransform, clearZoomTransition, stopPanInertia]);

  const dismissZoomHint = useCallback(() => {
    if (hintRevealFrameRef.current != null) {
      cancelAnimationFrame(hintRevealFrameRef.current);
      hintRevealFrameRef.current = null;
    }

    if (hintTimeoutRef.current != null) {
      clearTimeout(hintTimeoutRef.current);
      hintTimeoutRef.current = null;
    }

    setShowZoomHint(false);

    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(ZOOM_HINT_STORAGE_KEY, "1");
      } catch {
        // Ignore storage access failures for private browsing / SSR mismatch.
      }
    }
  }, []);

  const resetBoardZoom = useCallback(() => {
    suppressTapUntilRef.current = performance.now() + TAP_SUPPRESSION_MS;
    animateBoardTransform(MIN_BOARD_SCALE, 0, 0);
  }, [animateBoardTransform]);

  const startPanInertia = useCallback(() => {
    stopPanInertia();

    let previousTime = performance.now();

    const step = (now: number) => {
      const runtime = zoomRuntimeRef.current;
      const delta = Math.min(32, now - previousTime || 16);
      previousTime = now;

      const projectedX = runtime.x + runtime.velocityX * delta;
      const projectedY = runtime.y + runtime.velocityY * delta;
      const clampedOffset = clampBoardOffset(runtime.scale, projectedX, projectedY);

      if (clampedOffset.x !== projectedX) runtime.velocityX *= 0.35;
      if (clampedOffset.y !== projectedY) runtime.velocityY *= 0.35;

      applyBoardTransform(runtime.scale, projectedX, projectedY);

      const friction = Math.pow(PAN_INERTIA_FRICTION, delta / 16);
      runtime.velocityX *= friction;
      runtime.velocityY *= friction;

      if (
        Math.abs(runtime.velocityX) < PAN_INERTIA_MIN_SPEED &&
        Math.abs(runtime.velocityY) < PAN_INERTIA_MIN_SPEED
      ) {
        inertiaFrameRef.current = null;
        return;
      }

      inertiaFrameRef.current = requestAnimationFrame(step);
    };

    inertiaFrameRef.current = requestAnimationFrame(step);
  }, [applyBoardTransform, clampBoardOffset, stopPanInertia]);

  useEffect(() => {
    if (!isCoarsePointer) return undefined;

    try {
      if (window.localStorage.getItem(ZOOM_HINT_STORAGE_KEY) === "1") {
        return undefined;
      }
    } catch {
      // Ignore storage access failures and continue with the hint.
    }

    hintRevealFrameRef.current = window.requestAnimationFrame(() => {
      setShowZoomHint(true);
      hintTimeoutRef.current = setTimeout(() => {
        dismissZoomHint();
      }, ZOOM_HINT_TIMEOUT_MS);
    });

    return () => {
      if (hintRevealFrameRef.current != null) {
        cancelAnimationFrame(hintRevealFrameRef.current);
        hintRevealFrameRef.current = null;
      }
      if (hintTimeoutRef.current != null) {
        clearTimeout(hintTimeoutRef.current);
        hintTimeoutRef.current = null;
      }
    };
  }, [dismissZoomHint, isCoarsePointer]);

  useEffect(() => {
    const shell = boardRef.current;
    if (!shell) return undefined;

    const handleResize = () => {
      const runtime = zoomRuntimeRef.current;
      applyBoardTransform(runtime.scale, runtime.x, runtime.y);
    };

    const observer = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(handleResize)
      : null;

    observer?.observe(shell);
    window.addEventListener("resize", handleResize);

    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", handleResize);
    };
  }, [applyBoardTransform]);

  useEffect(() => {
    if (!isCoarsePointer) return undefined;

    const shell = boardRef.current;
    if (!shell) return undefined;

    const beginSingleTouchPan = (touch: Touch, rect: DOMRect) => {
      const runtime = zoomRuntimeRef.current;
      runtime.mode = "pan";
      runtime.lastPoint = getTouchPoint(touch, rect);
      runtime.lastMidpoint = null;
      runtime.lastTime = performance.now();
      runtime.velocityX = 0;
      runtime.velocityY = 0;
      runtime.travel = 0;
    };

    const beginPinch = (firstTouch: Touch, secondTouch: Touch, rect: DOMRect) => {
      const runtime = zoomRuntimeRef.current;
      const firstPoint = getTouchPoint(firstTouch, rect);
      const secondPoint = getTouchPoint(secondTouch, rect);
      const midpoint = getMidpoint(firstPoint, secondPoint);

      runtime.mode = "pinch";
      runtime.lastPoint = null;
      runtime.lastMidpoint = midpoint;
      runtime.lastTime = performance.now();
      runtime.velocityX = 0;
      runtime.velocityY = 0;
      runtime.travel = 0;
      runtime.pinchStartDistance = Math.max(1, getDistance(firstPoint, secondPoint));
      runtime.pinchStartScale = runtime.scale;
      runtime.pinchAnchor = {
        x: (midpoint.x - rect.width / 2 - runtime.x) / runtime.scale,
        y: (midpoint.y - rect.height / 2 - runtime.y) / runtime.scale,
      };
    };

    const finishGesture = () => {
      const runtime = zoomRuntimeRef.current;
      const shouldSuppressTap =
        runtime.mode === "pinch" || runtime.travel > PAN_ACTIVATION_THRESHOLD;

      if (runtime.scale <= 1.01) {
        applyBoardTransform(MIN_BOARD_SCALE, 0, 0);
      } else if (runtime.mode === "pan" && runtime.travel > PAN_START_THRESHOLD) {
        startPanInertia();
      }

      runtime.mode = "idle";
      runtime.lastPoint = null;
      runtime.lastMidpoint = null;
      runtime.pinchAnchor = null;
      runtime.lastTime = 0;
      runtime.travel = 0;
      suppressTapUntilRef.current = shouldSuppressTap
        ? performance.now() + TAP_SUPPRESSION_MS
        : 0;
    };

    const handleTouchStart = (event: TouchEvent) => {
      stopPanInertia();
      dismissZoomHint();

      const rect = shell.getBoundingClientRect();
      if (event.touches.length >= 2) {
        beginPinch(event.touches[0], event.touches[1], rect);
        suppressTapUntilRef.current = performance.now() + TAP_SUPPRESSION_MS;
        if (event.cancelable) event.preventDefault();
        return;
      }

      if (event.touches.length === 1 && zoomRuntimeRef.current.scale > 1.01) {
        beginSingleTouchPan(event.touches[0], rect);
      }
    };

    const handleTouchMove = (event: TouchEvent) => {
      const rect = shell.getBoundingClientRect();
      const runtime = zoomRuntimeRef.current;
      const now = performance.now();

      if (event.touches.length >= 2) {
        const firstPoint = getTouchPoint(event.touches[0], rect);
        const secondPoint = getTouchPoint(event.touches[1], rect);
        const midpoint = getMidpoint(firstPoint, secondPoint);
        const distance = Math.max(1, getDistance(firstPoint, secondPoint));
        const nextScale = clamp(
          runtime.pinchStartScale * (distance / runtime.pinchStartDistance),
          MIN_BOARD_SCALE,
          MAX_BOARD_SCALE,
        );
        const anchor = runtime.pinchAnchor ?? { x: 0, y: 0 };
        const nextX = midpoint.x - rect.width / 2 - anchor.x * nextScale;
        const nextY = midpoint.y - rect.height / 2 - anchor.y * nextScale;

        if (runtime.lastMidpoint) {
          runtime.travel += Math.hypot(
            midpoint.x - runtime.lastMidpoint.x,
            midpoint.y - runtime.lastMidpoint.y,
          );
        }

        runtime.mode = "pinch";
        runtime.lastMidpoint = midpoint;
        runtime.lastTime = now;
        dismissZoomHint();
        applyBoardTransform(nextScale, nextX, nextY);
        suppressTapUntilRef.current = now + TAP_SUPPRESSION_MS;
        if (event.cancelable) event.preventDefault();
        return;
      }

      if (event.touches.length === 1 && runtime.scale > 1.01) {
        const nextPoint = getTouchPoint(event.touches[0], rect);
        const previousPoint = runtime.lastPoint ?? nextPoint;
        const deltaX = nextPoint.x - previousPoint.x;
        const deltaY = nextPoint.y - previousPoint.y;
        const elapsed = Math.max(1, now - runtime.lastTime);

        runtime.mode = "pan";
        runtime.lastPoint = nextPoint;
        runtime.lastTime = now;
        runtime.velocityX = deltaX / elapsed;
        runtime.velocityY = deltaY / elapsed;
        runtime.travel += Math.hypot(deltaX, deltaY);

        if (runtime.travel <= PAN_ACTIVATION_THRESHOLD) {
          return;
        }

        dismissZoomHint();
        applyBoardTransform(runtime.scale, runtime.x + deltaX, runtime.y + deltaY);
        suppressTapUntilRef.current = now + TAP_SUPPRESSION_MS;
        if (event.cancelable) event.preventDefault();
      }
    };

    const handleTouchEnd = (event: TouchEvent) => {
      const rect = shell.getBoundingClientRect();

      if (event.touches.length >= 2) {
        beginPinch(event.touches[0], event.touches[1], rect);
        if (event.cancelable) event.preventDefault();
        return;
      }

      if (event.touches.length === 1 && zoomRuntimeRef.current.scale > 1.01) {
        beginSingleTouchPan(event.touches[0], rect);
        if (event.cancelable) event.preventDefault();
        return;
      }

      finishGesture();
    };

    const handleTouchCancel = () => {
      finishGesture();
    };

    shell.addEventListener("touchstart", handleTouchStart, { passive: false });
    shell.addEventListener("touchmove", handleTouchMove, { passive: false });
    shell.addEventListener("touchend", handleTouchEnd, { passive: false });
    shell.addEventListener("touchcancel", handleTouchCancel, { passive: false });

    return () => {
      shell.removeEventListener("touchstart", handleTouchStart);
      shell.removeEventListener("touchmove", handleTouchMove);
      shell.removeEventListener("touchend", handleTouchEnd);
      shell.removeEventListener("touchcancel", handleTouchCancel);
    };
  }, [applyBoardTransform, dismissZoomHint, isCoarsePointer, startPanInertia, stopPanInertia]);

  useEffect(() => () => {
    stopPanInertia();
    clearZoomTransition();
    if (hintRevealFrameRef.current != null) {
      cancelAnimationFrame(hintRevealFrameRef.current);
      hintRevealFrameRef.current = null;
    }
    if (hintTimeoutRef.current != null) {
      clearTimeout(hintTimeoutRef.current);
      hintTimeoutRef.current = null;
    }
  }, [clearZoomTransition, stopPanInertia]);

  const handleCellClick = (row: number, col: number) => {
    if (
      isDraggingTile ||
      performance.now() < suppressTapUntilRef.current ||
      inertiaFrameRef.current != null ||
      zoomRuntimeRef.current.mode !== "idle"
    ) {
      return;
    }

    const key = `${row}-${col}`;
    if (pendingSet.has(key)) {
      removePendingTile(row, col);
      return;
    }
    if (lastMoveSet.has(key) && primaryWord) {
      setRevealedMoveKey(moveRevealKey);
      return;
    }
    if (showLastMoveInfo) {
      setRevealedMoveKey(null);
    }
    const boardLetter = grid[row]?.[col];
    if (boardLetter && boardLetter !== ".") return;
    onPlaceTile?.(row, col);
  };

  return (
    <div className="relative">
      <div
        ref={boardRef}
        data-dragging={isDraggingTile ? "true" : "false"}
        data-theme={boardTheme}
        data-shiny={boardShineEnabled ? "true" : "false"}
        data-mobile-touch={isCoarsePointer ? "true" : "false"}
        data-zoom-active="false"
        className="premium-board-shell relative p-2.5 sm:p-3"
      >
        <div className="premium-board-viewport relative">
          <div
            ref={zoomLayerRef}
            className="premium-board-zoom-layer relative"
            style={{ transform: "translate3d(0px, 0px, 0) scale(1)" }}
          >
            <div
              className="premium-board-grid grid gap-[2px]"
              style={{
                gridTemplateColumns: `repeat(${BOARD_SIZE}, 1fr)`,
                aspectRatio: "1",
              }}
            >
              {Array.from({ length: BOARD_SIZE }, (_, row) =>
                Array.from({ length: BOARD_SIZE }, (_, col) => {
                  const key = `${row}-${col}`;
                  const pending = pendingSet.get(key);
                  const boardLetter = grid[row]?.[col] ?? ".";
                  const letter = pending
                    ? (pending.blank_as || pending.letter)
                    : boardLetter !== "."
                      ? boardLetter
                      : null;
                  const showDragPreview =
                    dragPreview?.row === row &&
                    dragPreview?.col === col &&
                    !letter &&
                    !pending;

                  return (
                    <Cell
                      key={key}
                      row={row}
                      col={col}
                      letter={letter}
                      isBlank={pending ? pending.letter === "?" : blanks.has(key)}
                      isPending={!!pending}
                      isLastMove={lastMoveSet.has(key)}
                      isPreviewTarget={showDragPreview}
                      tileLayoutId={isCoarsePointer && pending ? `rack-tile-${pending.rackIndex}` : undefined}
                      hideTilePoints={isCoarsePointer && zoomActive}
                      useTouchPlacement={isCoarsePointer}
                      onCellClick={handleCellClick}
                    />
                  );
                }),
              )}
            </div>

            {hasLastMove && primaryWord && showLastMoveInfo ? (
              <div
                className="pointer-events-none absolute z-[3]"
                style={{
                  left: `${popupCenterX}%`,
                  top: popupTop,
                  transform: popupAbove ? "translate(-50%, -100%)" : "translate(-50%, 0)",
                }}
              >
                <div className="rounded-[1.15rem] border border-amber-300/38 bg-[linear-gradient(180deg,rgba(12,12,12,0.96),rgba(6,6,6,0.98))] px-4 py-3 text-center shadow-[0_18px_42px_rgba(0,0,0,0.42),0_0_18px_rgba(251,191,36,0.12)] backdrop-blur-sm">
                  <div className="flex items-center justify-center gap-2.5 sm:gap-3">
                    <span className="font-gold-shiny text-[1.32rem] font-black leading-none sm:text-[1.48rem]">
                      +{gameState?.last_move_points ?? 0}
                    </span>
                    <span className="text-[0.96rem] font-black uppercase leading-none tracking-[0.12em] text-white sm:text-[1rem]">
                      PTS
                    </span>
                    <span className="mx-2 text-white/42">•</span>
                    <span className="text-[0.92rem] font-black uppercase leading-none tracking-[0.12em] text-white sm:text-[0.98rem]">
                      COST:
                    </span>
                    <span className="font-gold-shiny text-[0.92rem] font-black leading-none tracking-[0.04em] sm:text-[0.98rem]">
                      {lastMoveCostValue}
                    </span>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div
        className={`pointer-events-none absolute inset-x-0 -bottom-3 z-[6] flex justify-center px-3 transition-all duration-200 ${
          showZoomHint ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
        }`}
      >
        <div className="pointer-events-auto inline-flex max-w-full items-center gap-2 rounded-full border border-sky-300/18 bg-[linear-gradient(135deg,rgba(12,21,31,0.96),rgba(7,12,20,0.98))] px-3 py-1.5 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-sky-100/84 shadow-[0_18px_34px_rgba(14,165,233,0.10)] backdrop-blur-sm">
          <span>Pinch to zoom</span>
          <span className="text-sky-100/30">•</span>
          <span>Drag to pan</span>
          <button
            type="button"
            onClick={dismissZoomHint}
            className="rounded-full border border-white/10 px-2 py-0.5 text-[0.62rem] tracking-[0.14em] text-sky-50/82 transition-colors hover:border-white/20 hover:text-white"
          >
            Hide
          </button>
        </div>
      </div>

      <div
        className={`absolute right-3 top-3 z-[7] transition-all duration-200 sm:right-4 sm:top-4 ${
          zoomActive ? "translate-y-0 opacity-100" : "pointer-events-none -translate-y-2 opacity-0"
        }`}
      >
        <button
          type="button"
          onClick={resetBoardZoom}
          className="inline-flex items-center gap-2 rounded-full border border-amber-200/26 bg-[linear-gradient(135deg,rgba(17,20,23,0.96),rgba(8,10,12,0.98))] px-3 py-2 text-[0.74rem] font-black uppercase tracking-[0.18em] text-amber-100 shadow-[0_18px_38px_rgba(0,0,0,0.28)] backdrop-blur-sm transition-all hover:border-amber-100/38 hover:text-white"
        >
          <span className="font-gold-shiny leading-none">Reset</span>
          <span className="text-white/34">zoom</span>
        </button>
      </div>
    </div>
  );
}
