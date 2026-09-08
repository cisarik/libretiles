"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useGameStore } from "@/hooks/useGameStore";
import type { AdminReplayPayload } from "@/lib/types";
import { boardMatches, buildReplayFrames, parseAdminReplay } from "@/lib/admin-replay";
import { useReplayEngine } from "@/hooks/useReplayEngine";
import { ReplayBoard } from "./ReplayBoard";
import { DualRackVisualizer } from "./DualRackVisualizer";
import { ReplayControls } from "./ReplayControls";
import { ReplayMoveDetails } from "./ReplayMoveDetails";
import styles from "./admin.module.css";

export function ReplayStudio({ gameId }: { gameId: string }) {
  const token = useGameStore((state) => state.token);
  const [payload, setPayload] = useState<AdminReplayPayload | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!token) return; let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      setPayload(null); setError("");
      return api.admin.getReplay(token, gameId);
    }).then((value) => { if (active && value) setPayload(parseAdminReplay(value)); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Replay could not be loaded."); });
    return () => { active = false; };
  }, [gameId, retry, token]);
  if (error) return <div className={`${styles.panel} mt-5 p-8 text-center`}><p className="text-rose-300">{error}</p><button className={`${styles.button} mt-4`} onClick={() => setRetry((value) => value + 1)}>Retry</button></div>;
  if (!payload) return <div className={`${styles.panel} mt-5 p-8`} aria-busy="true">Loading replay snapshot...</div>;
  return <LoadedReplay key={`${payload.game_id}-${payload.created_at}`} payload={payload} />;
}

function LoadedReplay({ payload }: { payload: AdminReplayPayload }) {
  const frames = useMemo(() => buildReplayFrames(payload), [payload]);
  const historyAvailable = payload.initial_state.initial_board !== null;
  const engine = useReplayEngine(historyAvailable ? payload.plies.length : 0);
  const frame = frames[engine.currentPlyIndex];
  const move = engine.currentPlyIndex > 0 ? payload.plies[engine.currentPlyIndex - 1] : null;
  const premium = useGameStore((state) => state.premiumLookEnabled);
  const partial = !historyAvailable;
  const endpointMismatch = !partial && !boardMatches(frames.at(-1)?.board ?? null, payload.final_state.board);
  const shownBoard = partial ? payload.final_state.board : frame.board!;
  const shownRacks = partial ? payload.final_state.racks : frame.racks;
  const shownScores = partial ? payload.final_state.scores : frame.scores;
  return <main tabIndex={0} onKeyDown={engine.onKeyDown} className="mt-5 outline-none"><header className="flex flex-wrap items-end justify-between gap-3"><div><div className="text-xs font-black uppercase tracking-[.3em] text-amber-400">Replay Studio</div><h1 className="mt-2 text-3xl font-black text-amber-100">{payload.game_id}</h1><p className="mt-1 text-sm text-stone-400">Fixed {payload.replay_status} snapshot · {payload.variant_slug} · {payload.status}</p></div></header>{partial ? <div className="mt-4 rounded-xl border border-rose-300/25 bg-rose-950/25 p-3 text-rose-200">Incomplete replay history: the initial board is unavailable. Showing the latest final-state snapshot; historical board playback is disabled.</div> : null}{endpointMismatch ? <div className="mt-4 rounded-xl border border-amber-300/25 bg-amber-950/25 p-3 text-amber-100">The reconstructed endpoint differs from the latest final-state snapshot.</div> : null}<div className={styles.studio}><div><ReplayBoard board={shownBoard} highlighted={partial ? [] : move?.board_delta ?? []} tilePoints={payload.tile_points} frameKey={engine.currentPlyIndex} /></div><div className={styles.sidebar}><DualRackVisualizer players={payload.players} racks={shownRacks} scores={shownScores} actingSlot={engine.currentPlyIndex === 0 ? payload.initial_state.starting_turn_slot : move?.player_slot ?? null} currentPlyIndex={engine.currentPlyIndex} tilePoints={payload.tile_points} premium={premium} /><ReplayMoveDetails move={move} players={payload.players} previousScores={engine.currentPlyIndex > 0 ? frames[engine.currentPlyIndex - 1].scores : undefined} /></div></div><div className="mt-4"><ReplayControls currentPlyIndex={engine.currentPlyIndex} totalPlies={engine.totalPlies} isPlaying={engine.isPlaying} playbackSpeed={engine.playbackSpeed} move={move} players={payload.players} onFirst={() => engine.goToPly(0)} onBack={engine.stepBackward} onToggle={engine.togglePlay} onForward={engine.stepForward} onLast={() => engine.goToPly(engine.totalPlies)} onSeek={engine.goToPly} onPause={engine.pause} onSpeed={engine.setSpeed} /></div></main>;
}
