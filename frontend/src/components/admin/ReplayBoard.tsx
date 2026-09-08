"use client";

import { BOARD_SIZE, PREMIUM_BOARD, PREMIUM_LABELS } from "@/lib/constants";
import { boardCellLetter, type AdminReplayBoardDelta, type BoardCell } from "@/lib/types";
import { Tile } from "@/components/tiles/Tile";
import styles from "./admin.module.css";

export function ReplayBoard({ board, highlighted, tilePoints, frameKey = 0, ariaLabel = "Replay board" }: { board: BoardCell[][]; highlighted: AdminReplayBoardDelta[]; tilePoints: Record<string, number>; frameKey?: number; ariaLabel?: string }) {
  const highlight = new Set(highlighted.map((cell) => `${cell.row}-${cell.col}`));
  return <div className={styles.board} aria-label={ariaLabel}>{Array.from({ length: BOARD_SIZE }, (_, row) => Array.from({ length: BOARD_SIZE }, (_, col) => {
    const cell = board[row]?.[col] ?? null;
    const letter = boardCellLetter(cell);
    const premium = PREMIUM_BOARD[row][col];
    const isHighlighted = highlight.has(`${row}-${col}`);
    const pointValue = cell?.token === "?" ? 0 : (cell ? tilePoints[cell.token] ?? 0 : 0);
    const label = letter ? `Row ${row + 1}, column ${col + 1}: ${letter}, ${pointValue} points${cell?.token === "?" ? ", blank" : ""}${isHighlighted ? ", placed this ply" : ""}` : `Row ${row + 1}, column ${col + 1}${premium ? `, ${premium}` : ""}`;
    return <div key={`${row}-${col}`} className={styles.cell} data-premium={premium || undefined} aria-label={label}>{letter ? <div key={isHighlighted ? `highlight-${frameKey}` : "tile"} className={`${styles.tileWrap} ${isHighlighted ? styles.highlight : ""}`}><Tile letter={letter} isBlank={cell?.token === "?"} isLastMove={isHighlighted} size="board" hoverable={false} tilePoints={tilePoints} /></div> : <span aria-hidden="true">{PREMIUM_LABELS[premium] || (row === 7 && col === 7 ? "★" : "")}</span>}</div>;
  }))}</div>;
}
