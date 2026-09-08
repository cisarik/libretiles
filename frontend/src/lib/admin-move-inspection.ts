import type { AdminReplayPly, WordResult } from "./types";
import { sanitizeInspectionTrace } from "./ai-inspection-trace";

export type DisplayWord = {
  word: WordResult;
  label: "Formed word" | "Primary word" | "Cross-word";
  equation: string | null;
  reconciles: boolean;
};

function cellTerm(cell: NonNullable<WordResult["inspection"]>["physical_cells"][number]): string {
  const token = cell.blank_as ?? cell.token;
  const points = cell.base_points * cell.letter_multiplier;
  const suffix = cell.premium_applied && cell.letter_multiplier > 1 ? ` ${cell.premium}` : "";
  return `${token}(${points}${suffix})`;
}

export function scoreEquation(word: WordResult): string | null {
  const detail = word.inspection;
  if (!detail) return null;
  const sum = detail.physical_cells.map(cellTerm).join(" + ");
  const multiplier = detail.word_multiplier;
  const wordPremiums = detail.physical_cells
    .filter((cell) => cell.premium_applied && (cell.premium === "DW" || cell.premium === "TW"))
    .map((cell) => cell.premium)
    .join("+");
  return `[${sum}]${multiplier > 1 ? ` × ${multiplier}${wordPremiums ? ` ${wordPremiums}` : ""}` : ""} = ${detail.word_total}`;
}

function primaryWordIndex(move: AdminReplayPly): number {
  if (move.words_formed.length < 2) return 0;
  const rows = new Set(move.placements.map((placement) => placement.row));
  const cols = new Set(move.placements.map((placement) => placement.col));
  const horizontal = rows.size === 1 && cols.size > 1;
  const vertical = cols.size === 1 && rows.size > 1;
  return Math.max(move.words_formed.findIndex((word) => {
    const coords = word.coords ?? [];
    if (coords.length < 2) return false;
    return horizontal
      ? coords.every((cell) => cell.row === coords[0].row)
      : vertical
        ? coords.every((cell) => cell.col === coords[0].col)
        : coords.every((cell) => cell.row === coords[0].row);
  }), 0);
}

export function inspectMoveWords(move: AdminReplayPly): DisplayWord[] {
  const primary = primaryWordIndex(move);
  return move.words_formed.map((word, index) => ({
    word,
    label: move.words_formed.length === 1 ? "Formed word" : index === primary ? "Primary word" : "Cross-word",
    equation: scoreEquation(word),
    reconciles: !word.inspection || (word.inspection.word_total === word.score && word.inspection.physical_cells.reduce((sum, cell) => sum + cell.base_points * cell.letter_multiplier, 0) * word.inspection.word_multiplier === word.inspection.word_total),
  }));
}

export function hasRecordedBingo(move: AdminReplayPly): boolean {
  return move.placements.length === 7 && move.points === move.words_formed.reduce((sum, word) => sum + word.score, 0) + 50;
}

export function moveInspectionTrace(move: AdminReplayPly) {
  return sanitizeInspectionTrace(move.ai_metadata.inspection_trace);
}
