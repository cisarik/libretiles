"use client";

import { useRef, useState } from "react";
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

function formatUsdPopup(value?: string | null): string {
  if (!value) return "$0.000000";
  const normalized = value.trim();
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) return "$0.000000";
  const [whole, fraction = ""] = normalized.split(".");
  return `$${whole}.${(fraction + "000000").slice(0, 6)}`;
}

export function Board({ dragPreview, isDraggingTile }: BoardProps) {
  const gameState = useGameStore((s) => s.gameState);
  const pendingTiles = useGameStore((s) => s.pendingTiles);
  const removePendingTile = useGameStore((s) => s.removePendingTile);
  const boardTheme = useGameStore((s) => s.boardTheme);
  const boardShineEnabled = useGameStore((s) => s.boardShineEnabled);
  const boardRef = useRef<HTMLDivElement | null>(null);
  const [revealedMoveKey, setRevealedMoveKey] = useState<string | null>(null);

  usePremiumBoardLighting(boardRef, isDraggingTile || !boardShineEnabled);

  const grid = gameState?.board ?? Array(BOARD_SIZE).fill(".".repeat(BOARD_SIZE));
  const blanks = new Set(
    (gameState?.blanks ?? []).map((b) => `${b.row}-${b.col}`),
  );
  const lastMoveCells = gameState?.last_move_cells ?? [];
  const lastMoveWords = gameState?.last_move_words ?? [];
  const primaryWordCoords = lastMoveWords[0]?.coords ?? lastMoveCells;
  const lastMoveSet = new Set(primaryWordCoords.map((cell) => `${cell.row}-${cell.col}`));
  const lastMoveBilling = gameState?.last_move_billing;
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
  const lastMoveCost = formatUsdPopup(lastMoveBilling?.charged_usd);
  const moveRevealKey = `${gameState?.move_count ?? 0}:${primaryWord ?? ""}`;
  const showLastMoveInfo = revealedMoveKey === moveRevealKey;

  const handleCellClick = (row: number, col: number) => {
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
    // Tap-to-place handled by parent via store
  };

  return (
    <div
      ref={boardRef}
      data-dragging={isDraggingTile ? "true" : "false"}
      data-theme={boardTheme}
      data-shiny={boardShineEnabled ? "true" : "false"}
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
                isLastMove={lastMoveSet.has(key)}
                isPreviewTarget={showDragPreview}
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
            <div className="font-gold-shiny text-[1.22rem] font-black uppercase leading-none tracking-[0.08em] sm:text-[1.36rem]">
              {primaryWord}
            </div>
            <div className="mt-2 text-[0.96rem] font-semibold uppercase tracking-[0.1em] text-white/92 sm:text-[1.04rem]">
              +{gameState?.last_move_points ?? 0} pts
              <span className="mx-2 text-white/42">•</span>
              Cost {lastMoveCost}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
