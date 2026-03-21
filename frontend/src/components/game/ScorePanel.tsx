"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";

function formatRoundedCreditUsd(value?: string | null) {
  if (value == null || value === "") return "$--";
  const numeric = Number.parseFloat(value);
  if (!Number.isFinite(numeric)) return "$--";
  return `$${Math.round(numeric)}`;
}

function AnimatedScore({ score, label }: { score: number; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <span className="text-[0.9rem] font-semibold uppercase tracking-[0.24em] text-white sm:text-[1rem]">
        {label}
      </span>
      <AnimatePresence mode="popLayout">
        <motion.span
          key={score}
          initial={{ y: -10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 10, opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 20 }}
          className="font-gold-shiny text-[2.25rem] font-black tabular-nums sm:text-[2.65rem]"
        >
          {score}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

interface ScorePanelProps {
  aiModelDisplayName?: string | null;
  creditBalance?: string | null;
  frameBorderColor?: string;
  onOpenRivalPicker: () => void;
  onNewGame: () => void;
  onGiveUp: () => void;
  onOpenSettings: () => void;
  startingNewGame?: boolean;
  givingUp?: boolean;
  disableGiveUp?: boolean;
}

export function ScorePanel({
  aiModelDisplayName,
  creditBalance,
  frameBorderColor,
  onOpenRivalPicker,
  onNewGame,
  onGiveUp,
  onOpenSettings,
  startingNewGame = false,
  givingUp = false,
  disableGiveUp = false,
}: ScorePanelProps) {
  const gameState = useGameStore((s) => s.gameState);
  const lastMoveResult = useGameStore((s) => s.lastMoveResult);

  const slots = gameState?.slots ?? [];
  const humanSlot = slots.find((s) => !s.is_ai);
  const aiSlot = slots.find((s) => s.is_ai);

  return (
    <div
      className="relative rounded-[1.55rem] border border-white/8 bg-black p-4 shadow-[0_24px_56px_rgba(0,0,0,0.28)] sm:p-5"
      style={frameBorderColor ? { borderColor: frameBorderColor } : undefined}
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] lg:items-center lg:gap-6">
        <div className="min-w-0">
          <div className="min-w-0 pt-1">
            <button
              type="button"
              onClick={onOpenRivalPicker}
              className="max-w-full truncate font-gold-shiny text-[1.85rem] font-black leading-none transition-opacity hover:opacity-90 sm:text-[2.08rem] lg:text-[2.2rem]"
              title="Choose the rival"
            >
              {aiModelDisplayName ?? "AI Rival"}
            </button>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <div className="inline-flex h-[3.2rem] items-center rounded-full border border-amber-300/22 bg-[linear-gradient(145deg,rgba(39,26,12,0.88),rgba(14,11,8,0.92))] px-4 shadow-[0_18px_36px_rgba(0,0,0,0.22)] sm:h-[3.35rem] sm:px-5">
              <span className="font-gold-money text-[1.72rem] font-black leading-none sm:text-[1.92rem]">
                {formatRoundedCreditUsd(creditBalance)}
              </span>
            </div>

            <button
              onClick={onOpenSettings}
              className="inline-flex h-[3.2rem] items-center gap-2 rounded-full border border-amber-300/18 bg-[linear-gradient(145deg,rgba(31,23,16,0.86),rgba(13,10,8,0.92))] px-4 shadow-[0_14px_28px_rgba(0,0,0,0.18)] transition-all hover:border-amber-200/34 hover:bg-[linear-gradient(145deg,rgba(46,32,18,0.92),rgba(17,12,8,0.96))] sm:h-[3.35rem] sm:px-5"
              title="Settings"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-amber-100/90"
              >
                <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              <span className="font-gold-shiny text-[1.38rem] font-black leading-none sm:text-[1.46rem]">
                Settings
              </span>
            </button>
          </div>
        </div>

        <div className="flex items-end justify-center gap-5 sm:gap-8 lg:justify-self-center">
          <AnimatedScore
            score={humanSlot?.score ?? 0}
            label={humanSlot?.username ?? "ITRISY"}
          />

          <div className="pb-1 text-[1.75rem] font-semibold uppercase tracking-[0.16em] text-white sm:text-[2rem]">
            vs
          </div>

          <AnimatedScore
            score={aiSlot?.score ?? 0}
            label={aiSlot?.username ?? "AI"}
          />
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2 lg:justify-end lg:justify-self-end">
          <button
            onClick={onGiveUp}
            disabled={disableGiveUp}
            className="rounded-full border border-rose-400/22 bg-rose-500/10 px-4 py-2.5 shadow-[0_10px_24px_rgba(244,63,94,0.10)] transition-all hover:border-rose-300/40 hover:bg-rose-500/14 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <span className="font-gold-shiny text-[1.38rem] font-black leading-none sm:text-[1.46rem]">
              {givingUp ? "Giving up..." : "Give up"}
            </span>
          </button>
          <button
            onClick={onNewGame}
            disabled={startingNewGame}
            className="rounded-full border border-amber-200/40 bg-[linear-gradient(135deg,rgba(251,191,36,0.18),rgba(245,158,11,0.08))] px-4 py-2.5 shadow-[0_10px_24px_rgba(251,191,36,0.12),0_0_28px_rgba(251,191,36,0.12)] transition-all hover:border-amber-100/60 hover:bg-[linear-gradient(135deg,rgba(251,191,36,0.24),rgba(245,158,11,0.12))] hover:shadow-[0_12px_28px_rgba(251,191,36,0.18),0_0_34px_rgba(251,191,36,0.18)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span className="font-gold-shiny text-[1.38rem] font-black leading-none sm:text-[1.46rem]">
              {startingNewGame ? "Starting..." : "New game"}
            </span>
          </button>
        </div>
      </div>

      <AnimatePresence>
        {lastMoveResult?.points && lastMoveResult.points > 0 && (
          <motion.div
            initial={{ scale: 0, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 500 }}
            className="absolute -top-8 font-gold-shiny text-xl font-black"
          >
            +{lastMoveResult.points}
            {lastMoveResult.bingo && " BINGO!"}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
