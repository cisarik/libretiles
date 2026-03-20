"use client";

import { useDroppable } from "@dnd-kit/core";
import { motion } from "framer-motion";
import { PREMIUM_BOARD, PREMIUM_COLORS, PREMIUM_LABELS } from "@/lib/constants";
import { Tile } from "@/components/tiles/Tile";

interface CellProps {
  row: number;
  col: number;
  letter: string | null;
  isBlank: boolean;
  isPending: boolean;
  isLastMove: boolean;
  onCellClick: (row: number, col: number) => void;
}

export function Cell({
  row,
  col,
  letter,
  isBlank,
  isPending,
  isLastMove,
  onCellClick,
}: CellProps) {
  const premium = PREMIUM_BOARD[row][col];
  const colors = PREMIUM_COLORS[premium];
  const label = PREMIUM_LABELS[premium];
  const isCenter = row === 7 && col === 7;

  const { setNodeRef, isOver } = useDroppable({
    id: `cell-${row}-${col}`,
    data: { row, col },
  });

  return (
    <div
      ref={setNodeRef}
      onClick={() => onCellClick(row, col)}
      className={`
        relative flex items-center justify-center aspect-square
        border border-stone-700/30 rounded-sm transition-colors duration-150
        ${!letter ? colors.bg : ""}
        ${isOver && !letter ? "bg-amber-400/30 ring-1 ring-amber-400" : ""}
        ${isLastMove && letter ? "ring-1 ring-emerald-400/50" : ""}
        ${!letter && !premium ? "bg-stone-800/40" : ""}
      `}
    >
      {letter ? (
        <motion.div
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
      ) : label ? (
        <span className={`text-[0.5rem] font-semibold ${colors.text} opacity-70`}>
          {label}
        </span>
      ) : isCenter ? (
        <span className="text-lg opacity-30">★</span>
      ) : null}
    </div>
  );
}
