/**
 * Frozen baseline user prompt generator from commit f6b6fff42736c5124b508fde319f8bf5ae96cfc3.
 *
 * Test-only oracle preservation: ensures the historical BASELINE_USER_PROMPT_SHA256
 * byte oracle remains provably frozen and verifiable even as modern prompt formats evolve.
 */

import {
  type MoveUserPromptContext,
  UnstructuredMultigraphContextError,
  containsMultigraphToken,
  formatRackMultiset,
  isMultigraphToken,
} from "./prompts";
import { boardCellLetter, type BoardCell } from "./types";

const BOARD_SIZE = 15;
const GRID_ROW = /^[\p{L}.]{15}$/u;

const ENGLISH_TILE_VALUES =
  "A=1 B=3 C=3 D=2 E=1 F=4 G=2 H=4 I=1 J=8 K=5 L=1 M=3 " +
  "N=1 O=1 P=3 Q=10 R=1 S=1 T=1 U=1 V=4 W=4 X=8 Y=4 Z=10 ?=0";

const TOKEN_GRID_LEGEND =
  "TOKEN GRID — each row lists 15 columns separated by '|'. '.' is an empty " +
  "square. ONE tile may be several letters (SZ, DZS), so a column is a whole " +
  "tile, never a letter. '?=CS' is a blank played as CS and scores zero.";

function extractGridRows(compactState: string): string[] {
  const rows: string[] = [];
  for (const line of compactState.split("\n")) {
    const trimmed = line.trim();
    if (GRID_ROW.test(trimmed)) {
      rows.push(trimmed.toUpperCase());
    }
  }
  return rows.slice(0, 15);
}

function renderLabeledBoard(rows: string[]): string {
  return rows
    .map((row, index) => `row ${String(index).padStart(2, "0")} |${row}|`)
    .join("\n");
}

function cellRowsFromGridStrings(rows: string[]): BoardCell[][] {
  return rows.map((row) =>
    [...row].map((character) =>
      character === "." ? null : { token: character, blank_as: null },
    ),
  );
}

function isCellGrid(value: unknown): value is BoardCell[][] {
  if (!Array.isArray(value) || value.length !== BOARD_SIZE) return false;
  return value.every(
    (row) => Array.isArray(row) && row.length === BOARD_SIZE,
  );
}

function occupantTokens(rows: BoardCell[][]): string[] {
  const tokens: string[] = [];
  for (const row of rows) {
    for (const cell of row) {
      const token = boardCellLetter(cell);
      if (token) tokens.push(token);
    }
  }
  return tokens;
}

function anchorsFromCells(rows: BoardCell[][]): string {
  if (rows.length !== BOARD_SIZE) {
    return "(7,7)";
  }
  let occupied = 0;
  const anchors = new Set<string>();
  const dirs: Array<[number, number]> = [
    [-1, 0],
    [1, 0],
    [0, -1],
    [0, 1],
  ];
  for (let row = 0; row < BOARD_SIZE; row += 1) {
    for (let col = 0; col < BOARD_SIZE; col += 1) {
      if (!boardCellLetter(rows[row][col] ?? null)) continue;
      occupied += 1;
      for (const [dRow, dCol] of dirs) {
        const nextRow = row + dRow;
        const nextCol = col + dCol;
        if (nextRow < 0 || nextRow > 14 || nextCol < 0 || nextCol > 14) continue;
        if (!boardCellLetter(rows[nextRow][nextCol] ?? null)) {
          anchors.add(`(${nextRow},${nextCol})`);
        }
      }
    }
  }
  if (occupied === 0) {
    return "(7,7) — center; first move must cover this square";
  }
  return [...anchors].sort().join(" ");
}

function renderPackedCellBoard(rows: BoardCell[][]): string {
  return renderLabeledBoard(
    rows.map((row) =>
      row.map((cell) => boardCellLetter(cell) ?? ".").join(""),
    ),
  );
}

function renderTokenGridBoard(rows: BoardCell[][]): string {
  return rows
    .map((row, index) => {
      const faces = row.map((cell) => {
        if (!cell || !cell.token) return ".";
        if (cell.blank_as) return `?=${cell.blank_as}`;
        return cell.token;
      });
      return `row ${String(index).padStart(2, "0")} |${faces.join("|")}|`;
    })
    .join("\n");
}

function snapshotTilePoints(
  context: MoveUserPromptContext,
): Record<string, number> | null {
  const raw = context.tile_points ?? context.ai_state.tile_points;
  if (!raw || typeof raw !== "object") return null;
  const entries = Object.entries(raw).filter(
    (entry): entry is [string, number] =>
      typeof entry[1] === "number" && Number.isFinite(entry[1]),
  );
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

function formatTileValues(points: Record<string, number> | null): string {
  if (!points) return ENGLISH_TILE_VALUES;
  return Object.entries(points)
    .map(([letter, value]) => `${letter}=${value}`)
    .join(" ");
}

function tileSnapshotTokens(context: MoveUserPromptContext): string[] {
  const points = snapshotTilePoints(context);
  return [
    ...new Set([
      ...(points ? Object.keys(points) : []),
      ...(context.alphabet ?? []),
    ]),
  ];
}

/**
 * Historical baseline user prompt builder frozen at f6b6fff42736c5124b508fde319f8bf5ae96cfc3.
 */
export function baselineBuildMoveUserPrompt(context: MoveUserPromptContext): string {
  const tileValues = formatTileValues(snapshotTilePoints(context));

  const premiumLegend =
    "TW=Triple Word, DW=Double Word, TL=Triple Letter, DL=Double Letter";

  const rawGrid = context.ai_state.grid;
  const rawRack = context.ai_state.ai_rack;
  const structured = isCellGrid(rawGrid) && Array.isArray(rawRack);
  const snapshotMultigraphs = tileSnapshotTokens(context).filter(isMultigraphToken);

  if (!structured && snapshotMultigraphs.length > 0) {
    throw new UnstructuredMultigraphContextError(snapshotMultigraphs);
  }

  const legacyRows = structured ? [] : extractGridRows(context.compact_state);
  const cells = structured
    ? (rawGrid as BoardCell[][])
    : cellRowsFromGridStrings(legacyRows);
  const rack = structured ? (rawRack as string[]) : rawRack;

  const multigraph =
    snapshotMultigraphs.length > 0 ||
    containsMultigraphToken(occupantTokens(cells)) ||
    containsMultigraphToken(Array.isArray(rack) ? rack : []);

  const renderable = cells.length === BOARD_SIZE;
  const boardRendered = !renderable
    ? context.compact_state
    : multigraph
      ? `${TOKEN_GRID_LEGEND}\n${renderTokenGridBoard(cells)}`
      : renderPackedCellBoard(cells);
  const anchors = anchorsFromCells(cells);

  return `RACK: ${formatRackMultiset(rack)}
TILE VALUES: ${tileValues}
PREMIUM LEGEND: ${premiumLegend}
${context.is_first_move ? "THIS IS THE FIRST MOVE — must cover center (7,7)." : ""}

BOARD (row, col are both 0..14; center is (7,7)):
${boardRendered}

ANCHORS (search context, not answers):
${anchors}

SEARCH:
- Call validateMove first with your best legal placement.
- After a rejection, pivot to a different placement.
- Backend validation decides legality; a validated result is the only success signal.

CURRENT BOARD STATE:
${context.compact_state}

Find the best legal placement among your validated results.`;
}
