"use client";

import { useRef } from "react";
import { useDroppable } from "@dnd-kit/core";
import { PREMIUM_BOARD, PREMIUM_LABELS } from "@/lib/constants";
import { Tile } from "@/components/tiles/Tile";

const MOBILE_TAP_MOVE_TOLERANCE = 10;

interface CellProps {
  row: number;
  col: number;
  letter: string | null;
  isBlank: boolean;
  isPending: boolean;
  isLastMove: boolean;
  isPreviewTarget: boolean;
  tileLayoutId?: string;
  hideTilePoints?: boolean;
  useTouchPlacement?: boolean;
  onCellClick: (row: number, col: number) => void;
}

export function Cell({
  row,
  col,
  letter,
  isBlank,
  isPending,
  isLastMove,
  isPreviewTarget,
  tileLayoutId,
  hideTilePoints = false,
  useTouchPlacement = false,
  onCellClick,
}: CellProps) {
  const premium = PREMIUM_BOARD[row][col];
  const label = PREMIUM_LABELS[premium];
  const isCenter = row === 7 && col === 7;
  const touchGestureRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  const { setNodeRef } = useDroppable({
    id: `cell-${row}-${col}`,
    data: { row, col },
  });

  return (
    <div
      ref={setNodeRef}
      data-premium={premium || undefined}
      onClick={!useTouchPlacement ? () => onCellClick(row, col) : undefined}
      onTouchStart={useTouchPlacement ? (event) => {
        const touch = event.touches[0];
        if (!touch) return;
        touchGestureRef.current = { x: touch.clientX, y: touch.clientY, moved: false };
      } : undefined}
      onTouchMove={useTouchPlacement ? (event) => {
        const gesture = touchGestureRef.current;
        const touch = event.touches[0];
        if (!gesture || !touch) return;
        if (Math.hypot(touch.clientX - gesture.x, touch.clientY - gesture.y) > MOBILE_TAP_MOVE_TOLERANCE) {
          gesture.moved = true;
        }
      } : undefined}
      onTouchEnd={useTouchPlacement ? (event) => {
        const gesture = touchGestureRef.current;
        touchGestureRef.current = null;
        const touch = event.changedTouches[0];
        if (!gesture || !touch) return;
        const traveled = Math.hypot(touch.clientX - gesture.x, touch.clientY - gesture.y);
        if (gesture.moved || traveled > MOBILE_TAP_MOVE_TOLERANCE) return;
        event.preventDefault();
        window.requestAnimationFrame(() => {
          onCellClick(row, col);
        });
      } : undefined}
      onTouchCancel={useTouchPlacement ? () => {
        touchGestureRef.current = null;
      } : undefined}
      className={[
        "board-cell",
        premium ? "" : "board-cell--plain",
        letter ? "board-cell--occupied" : "board-cell--empty",
        isPreviewTarget ? "board-cell--preview-target" : "",
        isLastMove && letter ? "board-cell--last-move" : "",
      ].filter(Boolean).join(" ")}
      style={useTouchPlacement ? { touchAction: "manipulation" } : undefined}
    >
      {letter ? (
        <div className="board-cell__content">
          <Tile
            letter={letter}
            isBlank={isBlank}
            isPending={isPending}
            isLastMove={isLastMove}
            hidePoints={hideTilePoints}
            layoutId={tileLayoutId}
            size="board"
          />
        </div>
      ) : label ? (
        <span className="board-cell__label">
          {label}
        </span>
      ) : isCenter ? (
        <span className="board-cell__star">★</span>
      ) : null}
    </div>
  );
}
