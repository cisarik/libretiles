"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";

function AnimatedScore({ score, label }: { score: number; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <span className="text-xs font-medium text-stone-400 uppercase tracking-wider">
        {label}
      </span>
      <AnimatePresence mode="popLayout">
        <motion.span
          key={score}
          initial={{ y: -10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 10, opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 20 }}
          className="text-3xl font-bold tabular-nums"
        >
          {score}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

export function ScorePanel() {
  const gameState = useGameStore((s) => s.gameState);
  const lastMoveResult = useGameStore((s) => s.lastMoveResult);

  const slots = gameState?.slots ?? [];
  const humanSlot = slots.find((s) => !s.is_ai);
  const aiSlot = slots.find((s) => s.is_ai);

  return (
    <div className="flex items-center justify-center gap-8 p-4 bg-stone-900/60 backdrop-blur-sm rounded-xl shadow-xl">
      <AnimatedScore
        score={humanSlot?.score ?? 0}
        label={humanSlot?.username ?? "You"}
      />

      <div className="flex flex-col items-center gap-1">
        <span className="text-stone-600 text-2xl font-light">vs</span>
        <span className="text-xs text-stone-500">
          {gameState?.bag_remaining ?? 0} tiles left
        </span>
      </div>

      <AnimatedScore
        score={aiSlot?.score ?? 0}
        label={aiSlot?.username ?? "AI"}
      />

      <AnimatePresence>
        {lastMoveResult?.points && lastMoveResult.points > 0 && (
          <motion.div
            initial={{ scale: 0, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 500 }}
            className="absolute -top-8 text-amber-400 font-bold text-xl"
          >
            +{lastMoveResult.points}
            {lastMoveResult.bingo && " BINGO!"}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
