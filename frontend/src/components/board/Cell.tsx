"use client";

import { useDroppable } from "@dnd-kit/core";
import { motion } from "framer-motion";
import { PREMIUM_BOARD, PREMIUM_LABELS } from "@/lib/constants";
import { Tile } from "@/components/tiles/Tile";

interface CellProps {
  row: number;
  col: number;
  letter: string | null;
  isBlank: boolean;
  isPending: boolean;
  isLastMove: boolean;
  dragPreviewLetter: string | null;
  dragPreviewIsBlank: boolean;
  onCellClick: (row: number, col: number) => void;
}

export function Cell({
  row,
  col,
  letter,
  isBlank,
  isPending,
  isLastMove,
  dragPreviewLetter,
  dragPreviewIsBlank,
  onCellClick,
}: CellProps) {
  const premium = PREMIUM_BOARD[row][col];
  const label = PREMIUM_LABELS[premium];
  const isCenter = row === 7 && col === 7;
  const isPreviewTarget = !letter && !!dragPreviewLetter;

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
        <motion.div
          className="board-cell__content"
          initial={isPending ? { scale: 0, rotate: -10 } : false}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        >
          <Tile
            letter={letter}
            isBlank={isBlank}
            isPending={isPending}
            size="sm"
          />
        </motion.div>
      ) : dragPreviewLetter ? (
        <motion.div
          className="board-cell__drag-preview"
          initial={{ opacity: 0, scale: 0.72, y: 5 }}
          animate={{ opacity: 1, scale: 0.96, y: 0 }}
          transition={{ type: "spring", stiffness: 420, damping: 28 }}
        >
          <Tile
            letter={dragPreviewLetter}
            isBlank={dragPreviewIsBlank}
            size="sm"
          />
        </motion.div>
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
