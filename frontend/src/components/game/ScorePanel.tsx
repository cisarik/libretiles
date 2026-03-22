"use client";

import type { ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";

function formatCreditBalance(value?: string | null) {
  if (value == null || value === "") return "$--.---";
  const numeric = Number.parseFloat(value);
  if (!Number.isFinite(numeric)) return "$--.---";
  return `$${numeric.toFixed(3)}`;
}

function LuxeHoverText({
  children,
  className,
}: {
  children: string;
  className: string;
}) {
  return (
    <span className={`relative inline-grid place-items-center text-center align-middle ${className}`}>
      <span
        className="col-start-1 row-start-1 font-gold-shiny transition-opacity duration-200 group-hover:opacity-0"
      >
        {children}
      </span>
      <span
        aria-hidden="true"
        className="pointer-events-none col-start-1 row-start-1 font-white-shiny opacity-0 transition-opacity duration-200 group-hover:opacity-100"
      >
        {children}
      </span>
    </span>
  );
}

function AnimatedScore({
  score,
  label,
  containerClassName,
  labelClassName,
}: {
  score: number;
  label: ReactNode;
  containerClassName?: string;
  labelClassName?: string;
}) {
  return (
    <div className={`flex min-w-0 flex-col items-center gap-1 ${containerClassName ?? ""}`}>
      <div className={`min-w-0 text-center ${labelClassName ?? ""}`}>
        {label}
      </div>
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

function SettingsButton({
  onClick,
  className,
  textClassName,
  compactLabel = false,
}: {
  onClick: () => void;
  className?: string;
  textClassName?: string;
  compactLabel?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`group h-[2.8rem] shrink-0 items-center justify-center gap-2 rounded-full border border-amber-300/18 bg-[linear-gradient(145deg,rgba(31,23,16,0.86),rgba(13,10,8,0.92))] px-2.5 shadow-[0_14px_28px_rgba(0,0,0,0.18)] transition-all hover:border-white/42 hover:bg-[linear-gradient(145deg,rgba(78,64,46,0.96),rgba(26,21,16,0.98))] hover:shadow-[0_16px_30px_rgba(255,255,255,0.08),0_0_26px_rgba(255,255,255,0.06)] sm:h-[2.9rem] sm:px-3.5 ${className ?? "inline-flex"}`}
      title="Settings"
    >
      {compactLabel ? (
        <span className="text-[1.1rem] leading-none" aria-hidden="true">⚙️</span>
      ) : (
        <>
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
            className="shrink-0 text-amber-100/90 transition-colors duration-200 group-hover:text-white"
          >
            <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          <LuxeHoverText className={textClassName ?? "text-[0.92rem] font-black leading-none sm:text-[1.04rem]"}>
            Settings
          </LuxeHoverText>
        </>
      )}
    </button>
  );
}

function CreditReadout({ balance, className }: { balance?: string | null; className?: string }) {
  return (
    <div className={`inline-flex shrink-0 items-baseline justify-center gap-2 ${className ?? ""}`}>
      <span className="text-[0.94rem] font-semibold leading-none text-white/86 sm:text-[1rem]">
        Credit:
      </span>
      <span className="font-gold-money text-[1.22rem] font-black leading-none sm:text-[1.42rem]">
        {formatCreditBalance(balance)}
      </span>
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
  const aiModelLabel = aiModelDisplayName ?? "Choose rival";

  return (
    <div
      className="relative rounded-[1.55rem] border border-white/8 bg-black p-4 shadow-[0_24px_56px_rgba(0,0,0,0.28)] sm:p-5"
      style={frameBorderColor ? { borderColor: frameBorderColor } : undefined}
    >
      <div className="grid gap-3 xl:grid-cols-[16rem_minmax(0,1fr)_16rem] xl:grid-rows-[auto_auto] xl:items-end xl:gap-x-4 xl:gap-y-2">
        <div className="hidden min-w-0 xl:col-start-1 xl:row-start-1 xl:block xl:self-end">
          <div className="min-w-0 -translate-x-[5px] -translate-y-[5px] pt-1 lg:pl-0.5">
            <div className="font-gold-shiny text-[1.84rem] font-black leading-none sm:text-[2.02rem]">
              Libre Tiles
            </div>
          </div>
        </div>

        <div className="hidden items-center gap-2 xl:col-start-1 xl:row-start-2 xl:flex xl:self-end">
          <SettingsButton
            onClick={onOpenSettings}
            className="inline-flex"
            textClassName="text-[1.16rem] font-black leading-none sm:text-[1.2rem]"
          />
          <CreditReadout balance={creditBalance} />
        </div>

        <div className="grid grid-cols-[minmax(5.2rem,max-content)_auto_minmax(5.2rem,max-content)] items-end justify-center gap-3 self-center sm:grid-cols-[minmax(5.8rem,max-content)_auto_minmax(5.8rem,max-content)] sm:gap-5 xl:col-start-2 xl:row-span-2 xl:-translate-x-[10px] xl:justify-self-center xl:self-center">
          <AnimatedScore
            score={humanSlot?.score ?? 0}
            label={humanSlot?.username ?? "ITRISY"}
            containerClassName="min-w-[5.2rem] sm:min-w-[5.8rem]"
            labelClassName="text-[0.9rem] font-semibold uppercase tracking-[0.24em] text-white sm:text-[1rem]"
          />

          <div className="pb-1 text-center text-[1.38rem] font-semibold uppercase tracking-[0.14em] text-white sm:text-[1.55rem]">
            vs
          </div>

          <AnimatedScore
            score={aiSlot?.score ?? 0}
            containerClassName="relative min-w-[5.2rem] sm:min-w-[5.8rem]"
            labelClassName="text-[0.82rem] font-semibold tracking-[0.18em] text-white sm:text-[0.9rem]"
            label={(
              <div className="relative inline-flex items-center justify-center">
                <span className="mr-1.5 shrink-0 text-[0.96rem] leading-none" aria-hidden="true">🧠</span>
                <span className="shrink-0 uppercase text-white">AI:</span>
                <button
                  type="button"
                  onClick={onOpenRivalPicker}
                  className="group absolute left-full top-1/2 ml-3 hidden max-w-[13.8rem] -translate-y-1/2 overflow-hidden whitespace-nowrap text-left transition-[opacity,filter] hover:opacity-92 hover:brightness-110 lg:block"
                  title={aiModelLabel}
                >
                  <LuxeHoverText className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[1.14rem] font-black leading-none sm:text-[1.22rem]">
                    {aiModelLabel}
                  </LuxeHoverText>
                </button>
              </div>
            )}
          />
        </div>

        <div className="flex flex-nowrap items-center justify-center gap-1.5 pb-1 sm:gap-2 xl:col-start-3 xl:row-start-2 xl:justify-end xl:self-end xl:pb-0">
          <SettingsButton
            onClick={onOpenSettings}
            className="inline-flex xl:hidden"
            compactLabel
          />
          <CreditReadout
            balance={creditBalance}
            className="hidden sm:inline-flex xl:hidden"
          />
          <button
            onClick={onGiveUp}
            disabled={disableGiveUp}
            className="group inline-flex h-[2.8rem] shrink-0 items-center justify-center rounded-full border border-rose-400/22 bg-rose-500/10 px-2.5 shadow-[0_10px_24px_rgba(244,63,94,0.10)] transition-all hover:border-white/42 hover:bg-[linear-gradient(145deg,rgba(113,24,46,0.5),rgba(55,14,27,0.48))] hover:shadow-[0_14px_28px_rgba(255,255,255,0.07),0_0_24px_rgba(255,255,255,0.04)] disabled:cursor-not-allowed disabled:opacity-45 sm:h-[2.9rem] sm:px-4"
          >
            <LuxeHoverText className="text-[0.94rem] font-black leading-none sm:text-[1.2rem]">
              {givingUp ? "Giving up..." : "Give up"}
            </LuxeHoverText>
          </button>
          <button
            onClick={onNewGame}
            disabled={startingNewGame}
            className="group inline-flex h-[2.8rem] shrink-0 items-center justify-center rounded-full border border-amber-200/40 bg-[linear-gradient(135deg,rgba(251,191,36,0.18),rgba(245,158,11,0.08))] px-2.5 shadow-[0_10px_24px_rgba(251,191,36,0.12),0_0_28px_rgba(251,191,36,0.12)] transition-all hover:border-white/48 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.18),rgba(251,191,36,0.18),rgba(245,158,11,0.12))] hover:shadow-[0_14px_30px_rgba(255,255,255,0.08),0_0_34px_rgba(255,255,255,0.06)] disabled:cursor-not-allowed disabled:opacity-50 sm:h-[2.9rem] sm:px-4"
          >
            <LuxeHoverText className="text-[0.94rem] font-black leading-none sm:text-[1.2rem]">
              {startingNewGame ? "Starting..." : "New game"}
            </LuxeHoverText>
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
