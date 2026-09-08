"use client";

import styles from "./admin.module.css";

export type JudgeExplanation = { word: string; valid: boolean; reasoning: string; lexicon: string; modelId?: string | null };

export function JudgeExplanationModal({ explanation, onClose }: { explanation: JudgeExplanation; onClose: () => void }) {
  return <div className={styles.modalBackdrop} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="judge-explanation-title"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-black uppercase tracking-[.18em] text-amber-400">AI judge explanation · advisory only</p><h2 id="judge-explanation-title" className="mt-1 text-2xl font-black text-amber-50">{explanation.word}: {explanation.valid ? "Valid" : "Invalid"}</h2></div><button className={styles.button} type="button" onClick={onClose}>Close</button></div><dl className="mt-5 grid gap-4 text-sm"><div><dt className="font-black text-amber-200">Reasoning</dt><dd className="mt-1 text-stone-300">{explanation.reasoning}</dd></div><div><dt className="font-black text-amber-200">Lexicon recall</dt><dd className="mt-1 text-stone-300">{explanation.lexicon}</dd></div>{explanation.modelId ? <div><dt className="font-black text-amber-200">Judge model</dt><dd className="mt-1 text-stone-300">{explanation.modelId}</dd></div> : null}</dl><p className="mt-5 rounded-xl border border-amber-300/20 bg-amber-300/5 p-3 text-xs text-stone-400">WordAuthority remains the persisted scoring authority. An AI explanation never overrides the backend verdict.</p></section></div>;
}
