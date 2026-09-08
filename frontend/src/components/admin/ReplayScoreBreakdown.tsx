"use client";

import { useState } from "react";
import type { AdminReplayPly } from "@/lib/types";
import { hasRecordedBingo, inspectMoveWords } from "@/lib/admin-move-inspection";
import { JudgeExplanationModal, type JudgeExplanation } from "./JudgeExplanationModal";

export function ReplayScoreBreakdown({ move }: { move: AdminReplayPly }) {
  const [explanation, setExplanation] = useState<JudgeExplanation | null>(null);
  const words = inspectMoveWords(move);
  if (move.kind !== "place" || words.length === 0) {
    return <p className="text-sm text-stone-400">This move did not form a scored word.</p>;
  }
  const judgeMode = move.ai_metadata.judge_mode === "ai" || move.diagnostic_ply?.score_authority === "model";
  return <div className="space-y-3">{hasRecordedBingo(move) ? <span className="inline-flex rounded-full border border-amber-300/50 bg-amber-400/15 px-3 py-1 text-xs font-black text-amber-100">Bingo +50</span> : null}{words.map(({ word, label, equation, reconciles }, index) => <article key={`${word.word}-${index}`} className="rounded-xl border border-amber-300/15 bg-black/25 p-3"><div className="flex flex-wrap items-baseline justify-between gap-2"><div><span className="text-xs font-black uppercase tracking-[.16em] text-amber-400">{label}</span><h4 className="mt-1 text-lg font-black text-stone-100">{word.word}</h4></div><strong className="text-amber-100">{word.score} points</strong></div>{equation ? <div className="mt-3 overflow-x-auto rounded-lg bg-stone-950 p-3 font-mono text-sm text-amber-100">{equation}</div> : <p className="mt-3 text-sm text-stone-400">Per-tile breakdown was not recorded.</p>}{word.inspection ? <div className="mt-3 text-sm text-stone-300"><div><strong>Backend certified:</strong> {word.inspection.authority.name} · {word.inspection.authority.valid ? "Valid" : "Invalid"}</div><div><strong>Lexicon:</strong> {word.inspection.authority.lexicon_source} ({word.inspection.authority.route === "two_tile" ? word.inspection.authority.two_tile_lexicon_id : word.inspection.authority.main_lexicon_id})</div><div><strong>Physical route:</strong> {word.inspection.authority.physical_tile_count} tiles · {word.inspection.authority.route}</div></div> : <p className="mt-3 text-xs text-stone-500">Legacy stored move; detailed certification is unavailable.</p>}{judgeMode ? <button className="mt-3 rounded-lg border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-sm font-black text-amber-100" type="button" onClick={() => setExplanation({ word: word.word, valid: word.inspection?.authority.valid ?? true, reasoning: String(move.ai_metadata.judge_reasoning ?? "The selected AI judge explanation was not persisted for this move."), lexicon: word.inspection?.authority.lexicon_source ?? "No recorded lexicon recall", modelId: typeof move.ai_metadata.judge_model_id === "string" ? move.ai_metadata.judge_model_id : null })}>⚖️ AI Judge verdict</button> : null}{!reconciles ? <p className="mt-2 text-sm font-bold text-rose-300">Recorded detail does not reconcile with the stored word total.</p> : null}</article>)}{explanation ? <JudgeExplanationModal explanation={explanation} onClose={() => setExplanation(null)} /> : null}</div>;
}
