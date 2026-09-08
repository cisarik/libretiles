"use client";

import type { AdminReplayPly } from "@/lib/types";
import type { ReplaySpeed } from "@/lib/admin-replay-engine";
import { playerLabel } from "./DualRackVisualizer";
import type { AdminReplayPlayer } from "@/lib/types";
import styles from "./admin.module.css";

export function replayTicker(index: number, total: number, move: AdminReplayPly | null, players: AdminReplayPlayer[]): string {
  if (!move) return `Ply 0 of ${total}: Initial position`;
  const who = playerLabel(players.find((player) => player.slot === move.player_slot), move.player_slot);
  if (move.kind === "place") return `Ply ${index} of ${total}: ${who} played ${move.words_formed.map((word) => word.word).join(", ") || "tiles"} for ${move.points} points`;
  if (move.kind === "exchange") return `Ply ${index} of ${total}: ${who} exchanged ${move.tiles_exchanged} tiles`;
  return `Ply ${index} of ${total}: ${who} ${move.kind === "give_up" ? "gave up" : "passed"}`;
}

export function ReplayControls(props: { currentPlyIndex: number; totalPlies: number; isPlaying: boolean; playbackSpeed: ReplaySpeed; move: AdminReplayPly | null; players: AdminReplayPlayer[]; onFirst: () => void; onBack: () => void; onToggle: () => void; onForward: () => void; onLast: () => void; onSeek: (value: number) => void; onPause: () => void; onSpeed: (speed: ReplaySpeed) => void }) {
  const atStart = props.currentPlyIndex === 0; const atEnd = props.currentPlyIndex === props.totalPlies;
  return <section className={`${styles.panel} p-4`} aria-label="Replay playback controls"><div className={styles.controls}><button className={styles.button} onClick={props.onFirst} disabled={atStart} aria-label="First ply">&lt;&lt;</button><button className={styles.button} onClick={props.onBack} disabled={atStart} aria-label="Step backward">&lt;</button><button className={styles.button} onClick={props.onToggle} disabled={!props.totalPlies} aria-label={props.isPlaying ? "Pause replay" : atEnd ? "Replay from start" : "Play replay"}>{props.isPlaying ? "Pause" : "Play"}</button><button className={styles.button} onClick={props.onForward} disabled={atEnd} aria-label="Step forward">&gt;</button><button className={styles.button} onClick={props.onLast} disabled={atEnd} aria-label="Last ply">&gt;&gt;</button>{([0.5, 1, 2] as ReplaySpeed[]).map((speed) => <button key={speed} className={styles.button} aria-pressed={props.playbackSpeed === speed} onClick={() => props.onSpeed(speed)}>{speed}x</button>)}</div><label className="mt-4 block text-sm text-stone-300">Replay timeline<input className={`${styles.range} mt-2`} type="range" min={0} max={props.totalPlies} step={1} value={props.currentPlyIndex} onPointerDown={props.onPause} onChange={(event) => props.onSeek(Number(event.target.value))} /></label><p className="mt-3 font-semibold text-amber-100" aria-live={props.isPlaying ? "off" : "polite"}>{replayTicker(props.currentPlyIndex, props.totalPlies, props.move, props.players)}</p></section>;
}
