"use client";

import Link from "next/link";

import type { SimulationRunnerPhase, SimulationSpeed } from "@/hooks/useSimulationRunner";
import { simulationLatestDelta, type SimulationState } from "@/lib/admin-simulation";
import { ReplayBoard } from "./ReplayBoard";
import { DualRackVisualizer } from "./DualRackVisualizer";
import styles from "./admin.module.css";

function moveCommentary(state: SimulationState, move: SimulationState["moves"][number]): string {
  const player = state.players.find((item) => item.slot === move.player_slot);
  const label = player?.model_display_name ?? `Player ${move.player_slot}`;
  if (move.kind === "pass") return `${label} passed.`;
  if (move.kind === "exchange") return `${label} exchanged ${move.tiles_exchanged} tiles.`;
  if (move.kind === "give_up") return `${label} gave up.`;
  const words = move.words.map((word) => word.word).filter(Boolean).join(", ");
  return `${label} played ${words || "tiles"} for ${move.points} points.`;
}

export function SimulationArena({ state, phase, speed, status, onPause, onResume, onStep, onStop, onSpeed }: { state: SimulationState; phase: SimulationRunnerPhase; speed: SimulationSpeed; status: string | null; onPause: () => void; onResume: () => void; onStep: () => void; onStop: () => void; onSpeed: (speed: SimulationSpeed) => void }) {
  const spread = state.scores[0] - state.scores[1];
  const terminalTitle = state.game_end_reason === "simulation_stopped" ? "Simulation stopped" : state.winner_slot === null ? "Draw" : `${state.players.find((player) => player.slot === state.winner_slot)?.model_display_name ?? `Player ${state.winner_slot}`} wins`;
  return (
    <div className={styles.arena}>
      <section className={styles.panel}>
        <ReplayBoard board={state.board} highlighted={simulationLatestDelta(state)} tilePoints={state.tile_points} frameKey={state.move_count} ariaLabel="Live simulation board" />
      </section>
      <aside className="grid gap-4">
        {state.game_over ? <section className={`${styles.panel} border-amber-300/50 p-5`}><p className="text-xs font-black uppercase tracking-[.18em] text-amber-400">Terminal position</p><h2 className="mt-2 text-3xl font-black text-amber-100">{terminalTitle}</h2><p className="mt-2 text-stone-300">{state.scores[0]} – {state.scores[1]} · spread {spread > 0 ? "+" : ""}{spread} · {state.game_end_reason}</p><Link className="mt-5 inline-flex rounded-xl bg-amber-300 px-5 py-3 font-black text-stone-950" href={state.replay_url}>Open in Replay Studio →</Link></section> : null}
        <DualRackVisualizer players={state.players} racks={state.racks} scores={state.scores} actingSlot={state.current_turn_slot} currentPlyIndex={state.move_count} tilePoints={state.tile_points} premium={false} live />
        <section className={`${styles.panel} p-4`}>
          <div className={styles.controls}>
            {phase === "running" ? <button className={styles.button} onClick={onPause}>Pause</button> : <button className={styles.button} onClick={onResume} disabled={state.game_over}>Resume</button>}
            <button className={styles.button} onClick={onStep} disabled={state.game_over || phase === "running"}>Step One Turn</button>
            <button className={styles.button} onClick={onStop} disabled={state.game_over}>Stop Simulation</button>
            <label className="ml-auto text-xs font-black uppercase tracking-wider text-stone-400">Speed <select className={`${styles.select} ml-2 w-auto`} value={speed} onChange={(event) => onSpeed(Number(event.target.value) as SimulationSpeed)}><option value={0.5}>0.5x</option><option value={1}>1x</option><option value={2}>2x</option></select></label>
          </div>
          <p className="mt-3 text-sm text-stone-400" aria-live="polite">{status ?? (phase === "paused" ? "Simulation paused." : "Waiting for the next committed turn.")}</p>
        </section>
        <section className={`${styles.panel} p-4`}>
          <div className={styles.scoreBar}><div className={spread >= 0 ? styles.scoreLead0 : ""} /><strong className="text-sm text-stone-300">{spread > 0 ? "+" : ""}{spread}</strong><div className={spread <= 0 ? styles.scoreLead1 : ""} /></div>
          <div className={`${styles.ticker} mt-4`} aria-label="Move commentary">{[...state.moves].reverse().map((move) => <article className={styles.tickerItem} key={move.seq}><span className="text-xs font-black text-amber-400">#{move.seq}</span><p className="text-sm text-stone-200">{moveCommentary(state, move)}</p></article>)}</div>
        </section>
      </aside>
    </div>
  );
}
