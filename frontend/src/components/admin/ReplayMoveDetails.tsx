import type { AdminReplayPly } from "@/lib/types";
import { playerLabel } from "./DualRackVisualizer";
import type { AdminReplayPlayer } from "@/lib/types";
import styles from "./admin.module.css";

export function ReplayMoveDetails({ move, players, previousScores }: { move: AdminReplayPly | null; players: AdminReplayPlayer[]; previousScores?: [number | null, number | null] }) {
  if (!move) return <section className={`${styles.panel} p-5`}><h2 className="text-xl font-black text-amber-100">Initial position</h2><p className="mt-2 text-stone-400">No ply has been applied.</p></section>;
  const player = playerLabel(players.find((item) => item.slot === move.player_slot), move.player_slot);
  const currentScore = move.cumulative_scores[move.player_slot];
  const previousScore = previousScores?.[move.player_slot];
  const adjustment = currentScore == null || previousScore == null ? null : currentScore - previousScore - move.points;
  return <section className={`${styles.panel} p-5`}><div className="text-xs font-black uppercase tracking-[.18em] text-amber-400">Stored sequence {move.seq}</div><h2 className="mt-2 text-xl font-black text-amber-100">{player}: {move.kind.replace("_", " ")}</h2><p className="mt-2 text-stone-300">Points gained: <strong>{move.points}</strong></p>{move.kind === "exchange" ? <p className="mt-2 text-stone-300">Exchanged {move.tiles_exchanged} tiles{move.exchanged_tiles ? `: ${move.exchanged_tiles.join(" ")}` : " (letters unavailable)"}</p> : null}{move.words_formed.length ? <p className="mt-3 text-sm text-stone-300">Words: {move.words_formed.map((word) => `${word.word} (${word.score})`).join(" · ")}</p> : null}{adjustment !== null && move.kind === "place" && adjustment !== 0 ? <p className="mt-4 text-sm text-amber-200">Recorded cumulative score includes adjustments beyond this move&apos;s {move.points} points.</p> : null}</section>;
}
