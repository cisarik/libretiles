"use client";

import type { AIPrompt } from "@/lib/types";
import styles from "./admin.module.css";

export function PromptPreviewModal({ prompt, onClose }: { prompt: AIPrompt; onClose: () => void }) {
  return <div className={styles.modalBackdrop} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="prompt-preview-title"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-black uppercase tracking-[.18em] text-amber-400">Strategic prompt inspection</p><h2 id="prompt-preview-title" className="mt-1 text-2xl font-black text-amber-50">{prompt.name}</h2></div><button className={styles.button} type="button" onClick={onClose} aria-label="Close prompt preview">Close</button></div><p className="mt-3 text-sm text-stone-400">This advisory SEARCH_PROFILE is combined with the non-overridable TypeScript CORE rules at runtime.</p><pre className={styles.promptPreview}>{prompt.prompt}</pre></section></div>;
}
