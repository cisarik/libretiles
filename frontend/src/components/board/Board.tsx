"use client";

import { useRef } from "react";
import { BOARD_SIZE } from "@/lib/constants";
import { Cell } from "./Cell";
import { useGameStore } from "@/hooks/useGameStore";
import { usePremiumBoardLighting } from "@/hooks/usePremiumBoardLighting";

interface BoardDragPreview {
  row: number;
  col: number;
}

interface BoardProps {
  dragPreview: BoardDragPreview | null;
  isDraggingTile: boolean;
}

export function Board({ dragPreview, isDraggingTile }: BoardProps) {
  const gameState = useGameStore((s) => s.gameState);
  const pendingTiles = useGameStore((s) => s.pendingTiles);
  const removePendingTile = useGameStore((s) => s.removePendingTile);
  const boardRef = useRef<HTMLDivElement | null>(null);

  usePremiumBoardLighting(boardRef, isDraggingTile);

  const grid = gameState?.board ?? Array(BOARD_SIZE).fill(".".repeat(BOARD_SIZE));
  const blanks = new Set(
    (gameState?.blanks ?? []).map((b) => `${b.row}-${b.col}`),
  );
  const pendingSet = new Map(
    pendingTiles.map((t) => [`${t.row}-${t.col}`, t]),
  );

  const handleCellClick = (row: number, col: number) => {
    const key = `${row}-${col}`;
    if (pendingSet.has(key)) {
      removePendingTile(row, col);
      return;
    }
    // Tap-to-place handled by parent via store
  };

  return (
    <div
      ref={boardRef}
      data-dragging={isDraggingTile ? "true" : "false"}
      className="premium-board-shell relative p-2.5 sm:p-3"
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
                isLastMove={false}
                isPreviewTarget={showDragPreview}
                onCellClick={handleCellClick}
              />
            );
          }),
        )}
      </div>
    </div>
  );
}
