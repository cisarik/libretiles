import type { PremiumType } from "./types";

export const BOARD_SIZE = 15;

export const PREMIUM_BOARD: PremiumType[][] = [
  ["TW","","","DL","","","","TW","","","","DL","","","TW"],
  ["","DW","","","","TL","","","","TL","","","","DW",""],
  ["","","DW","","","","DL","","DL","","","","DW","",""],
  ["DL","","","DW","","","","DL","","","","DW","","","DL"],
  ["","","","","DW","","","","","","DW","","","",""],
  ["","TL","","","","TL","","","","TL","","","","TL",""],
  ["","","DL","","","","DL","","DL","","","","DL","",""],
  ["TW","","","DL","","","","DW","","","","DL","","","TW"],
  ["","","DL","","","","DL","","DL","","","","DL","",""],
  ["","TL","","","","TL","","","","TL","","","","TL",""],
  ["","","","","DW","","","","","","DW","","","",""],
  ["DL","","","DW","","","","DL","","","","DW","","","DL"],
  ["","","DW","","","","DL","","DL","","","","DW","",""],
  ["","DW","","","","TL","","","","TL","","","","DW",""],
  ["TW","","","DL","","","","TW","","","","DL","","","TW"],
];

export const TILE_POINTS: Record<string, number> = {
  A: 1, B: 3, C: 3, D: 2, E: 1, F: 4, G: 2, H: 4, I: 1, J: 8,
  K: 5, L: 1, M: 3, N: 1, O: 1, P: 3, Q: 10, R: 1, S: 1, T: 1,
  U: 1, V: 4, W: 4, X: 8, Y: 4, Z: 10, "?": 0,
};

export const PREMIUM_COLORS: Record<PremiumType, { bg: string; text: string; glow: string }> = {
  TW: { bg: "bg-amber-500/20", text: "text-amber-300", glow: "shadow-amber-500/30" },
  DW: { bg: "bg-rose-500/20", text: "text-rose-300", glow: "shadow-rose-500/30" },
  TL: { bg: "bg-emerald-500/20", text: "text-emerald-300", glow: "shadow-emerald-500/30" },
  DL: { bg: "bg-sky-500/20", text: "text-sky-300", glow: "shadow-sky-500/30" },
  "": { bg: "", text: "", glow: "" },
};

export const PREMIUM_LABELS: Record<PremiumType, string> = {
  TW: "3W",
  DW: "2W",
  TL: "3L",
  DL: "2L",
  "": "",
};
