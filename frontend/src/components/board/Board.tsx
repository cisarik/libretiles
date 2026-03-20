"use client";

import { BOARD_SIZE } from "@/lib/constants";
import { Cell } from "./Cell";
import { useGameStore } from "@/hooks/useGameStore";

export function Board() {
  const gameState = useGameStore((s) => s.gameState);
  const pendingTiles = useGameStore((s) => s.pendingTiles);
  const removePendingTile = useGameStore((s) => s.removePendingTile);

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
    <div className="relative p-2 bg-stone-900/60 backdrop-blur-sm rounded-xl shadow-2xl shadow-black/50">
      <div
        className="grid gap-[1px]"
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

            return (
              <Cell
                key={key}
                row={row}
                col={col}
                letter={letter}
                isBlank={pending ? pending.letter === "?" : blanks.has(key)}
                isPending={!!pending}
                isLastMove={false}
                onCellClick={handleCellClick}
              />
            );
          }),
        )}
      </div>
    </div>
  );
}
