"use client";

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";
import { TILE_POINTS } from "@/lib/constants";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function MiniTile({ letter, highlight }: { letter: string; highlight: boolean }) {
  const pts = TILE_POINTS[letter.toUpperCase()] ?? 0;
  return (
    <div
      className={`
        relative w-8 h-8 rounded-md flex items-center justify-center
        font-bold text-sm uppercase select-none shrink-0
        ${highlight
          ? "bg-gradient-to-br from-amber-200 to-amber-300 text-amber-900 shadow-md shadow-amber-400/30 ring-1 ring-amber-400/50"
          : "bg-gradient-to-br from-stone-200 to-stone-300 text-stone-800 shadow-sm"
        }
      `}
    >
      <span className="leading-none">{letter}</span>
      {pts > 0 && (
        <span className="absolute bottom-0 right-0.5 text-[7px] font-medium opacity-60">
          {pts}
        </span>
      )}
    </div>
  );
}

function WordCandidate({
  word,
  score,
  valid,
  isBest,
  isNew,
  rank,
}: {
  word: string;
  score: number;
  valid: boolean;
  isBest: boolean;
  isNew: boolean;
  rank: number;
}) {
  const letters = word.toUpperCase().split("");

  return (
    <motion.div
      initial={isNew ? { opacity: 0, x: -30, scale: 0.9 } : false}
      animate={{ opacity: valid ? 1 : 0.35, x: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className={`
        flex items-center gap-2 px-2.5 py-2 rounded-xl transition-all
        ${isBest
          ? "bg-amber-500/15 border border-amber-400/30"
          : "bg-stone-800/30"
        }
      `}
    >
      {/* Rank */}
      <span className={`text-xs font-bold w-5 text-center shrink-0 ${
        isBest ? "text-amber-400" : valid ? "text-stone-500" : "text-stone-600"
      }`}>
        {valid ? `#${rank}` : "—"}
      </span>

      {/* Tiles */}
      <div className="flex gap-0.5 flex-1 min-w-0">
        {letters.map((ch, i) => (
          <MiniTile key={`${ch}-${i}`} letter={ch} highlight={isBest} />
        ))}
      </div>

      {/* Score */}
      <div className={`flex items-center gap-1 shrink-0 ${
        !valid ? "line-through opacity-50" : ""
      }`}>
        <span className={`text-lg font-black tabular-nums ${
          isBest ? "text-amber-300" : valid ? "text-stone-200" : "text-stone-500"
        }`}>
          {score}
        </span>
        <span className={`text-[10px] font-medium ${
          isBest ? "text-amber-400/70" : "text-stone-500"
        }`}>
          pts
        </span>
      </div>

      {/* Best badge */}
      {isBest && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 500 }}
          className="text-[10px] font-black text-amber-900 bg-amber-400 rounded-full px-1.5 py-0.5 shrink-0"
        >
          BEST
        </motion.div>
      )}
    </motion.div>
  );
}

function HourglassSimple({ urgent }: { urgent: boolean }) {
  const color = urgent ? "text-red-400" : "text-amber-400";
  return (
    <motion.div
      animate={{ rotate: [0, 180] }}
      transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
      className={`w-10 h-10 ${color}`}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M5 3h14M5 21h14M7 3v3.4a4 4 0 001.17 2.83L12 13l3.83-3.77A4 4 0 0017 6.4V3M7 21v-3.4a4 4 0 011.17-2.83L12 11l3.83 3.77A4 4 0 0017 17.6V21" />
      </svg>
    </motion.div>
  );
}

export function AIThinkingOverlay() {
  const aiThinking = useGameStore((s) => s.aiThinking);
  const aiCountdown = useGameStore((s) => s.aiCountdown);
  const aiCandidates = useGameStore((s) => s.aiCandidates);
  const aiStatusMessage = useGameStore((s) => s.aiStatusMessage);
  const feedEndRef = useRef<HTMLDivElement>(null);

  const urgent = aiCountdown > 0 && aiCountdown <= 10;

  const validSorted = [...aiCandidates]
    .filter((c) => c.valid)
    .sort((a, b) => b.score - a.score);
  const rejectedCount = Math.max(aiCandidates.length - validSorted.length, 0);

  const bestCandidate = validSorted[0] ?? null;

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [aiCandidates.length]);

  return (
    <AnimatePresence>
      {aiThinking && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center
            bg-black/15 backdrop-blur-[1px]"
        >
          <motion.div
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 28 }}
            className="w-[96vw] max-w-lg mb-2 sm:mb-0
              bg-stone-900/90 backdrop-blur-xl border border-stone-600/20
              rounded-2xl shadow-2xl shadow-black/40
              p-4 flex flex-col gap-3 max-h-[80vh]"
          >
            {/* Header: hourglass + timer */}
            <div className="flex items-center gap-3">
              <HourglassSimple urgent={urgent} />
              <div className="flex-1">
                <div className="text-stone-400 text-[10px] uppercase tracking-[0.2em] font-medium">
                  AI Thinking
                </div>
                {aiCountdown > 0 && (
                  <div className={`text-xl font-bold tabular-nums font-mono leading-tight ${
                    urgent ? "text-red-400 animate-pulse" : "text-amber-300"
                  }`}>
                    {formatTime(aiCountdown)}
                  </div>
                )}
                {aiStatusMessage && (
                  <div className="text-stone-500 text-xs mt-1 leading-snug max-w-xs">
                    {aiStatusMessage}
                  </div>
                )}
              </div>
              {bestCandidate && (
                <div className="text-right">
                  <div className="text-[10px] text-stone-500 uppercase tracking-wider">Best</div>
                  <div className="text-amber-300 font-black text-lg leading-tight">
                    {bestCandidate.score} pts
                  </div>
                </div>
              )}
            </div>

            {/* Candidate list */}
            {aiCandidates.length > 0 ? (
              <div className="flex flex-col gap-1.5 overflow-y-auto pr-0.5 flex-1 min-h-0">
                {/* Valid candidates, best first */}
                {validSorted.map((c, i) => (
                  <WordCandidate
                    key={`valid-${c.word}-${c.score}-${i}`}
                    word={c.word}
                    score={c.score}
                    valid={true}
                    isBest={i === 0}
                    isNew={c === aiCandidates[aiCandidates.length - 1]}
                    rank={i + 1}
                  />
                ))}
                {validSorted.length === 0 && rejectedCount > 0 && (
                  <div className="rounded-xl border border-white/6 bg-stone-800/28 px-3 py-3 text-center text-xs text-stone-500">
                    Filtering weak or invalid lines before showing a serious move...
                  </div>
                )}
                <div ref={feedEndRef} />
              </div>
            ) : (
              <div className="flex items-center justify-center gap-2 py-6">
                <div className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <motion.div
                      key={i}
                      animate={{ scale: [1, 1.5, 1], opacity: [0.3, 1, 0.3] }}
                      transition={{
                        repeat: Infinity,
                        duration: 0.8,
                        delay: i * 0.15,
                      }}
                      className="w-1.5 h-1.5 rounded-full bg-amber-400"
                    />
                  ))}
                </div>
                <span className="text-stone-500 text-xs">
                  Searching for moves...
                </span>
              </div>
            )}

            {/* Stats bar */}
            <div className="flex items-center justify-between text-[10px] text-stone-600 border-t border-stone-800/50 pt-2">
              <span>{aiCandidates.length} tried</span>
              <span>{validSorted.length} valid</span>
              <span>{rejectedCount > 0 ? `${rejectedCount} rejected` : ""}</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
