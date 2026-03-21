"use client";

import { useDroppable } from "@dnd-kit/core";
import { PREMIUM_BOARD, PREMIUM_LABELS } from "@/lib/constants";
import { Tile } from "@/components/tiles/Tile";

interface CellProps {
  row: number;
  col: number;
  letter: string | null;
  isBlank: boolean;
  isPending: boolean;
  isLastMove: boolean;
  isPreviewTarget: boolean;
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
  onCellClick,
}: CellProps) {
  const premium = PREMIUM_BOARD[row][col];
  const label = PREMIUM_LABELS[premium];
  const isCenter = row === 7 && col === 7;

  const { setNodeRef } = useDroppable({
    id: `cell-${row}-${col}`,
    data: { row, col },
  });

  return (
    <div
      ref={setNodeRef}
      data-premium={premium || undefined}
      onClick={() => onCellClick(row, col)}
      className={[
        "board-cell",
        premium ? "" : "board-cell--plain",
        letter ? "board-cell--occupied" : "board-cell--empty",
        isPreviewTarget ? "board-cell--preview-target" : "",
        isLastMove && letter ? "board-cell--last-move" : "",
      ].filter(Boolean).join(" ")}
    >
      {letter ? (
        <div className="board-cell__content">
          <Tile
            letter={letter}
            isBlank={isBlank}
            isPending={isPending}
            isLastMove={isLastMove}
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
