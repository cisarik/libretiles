"use client";

import { useGameStore } from "@/hooks/useGameStore";

interface GameControlsProps {
  onPlay: () => void;
  onExchange: () => void;
  onPass: () => void;
  disabled?: boolean;
}

export function GameControls({ onPlay, onExchange, onPass, disabled }: GameControlsProps) {
  const pendingTiles = useGameStore((s) => s.pendingTiles);
  const exchangeMode = useGameStore((s) => s.exchangeMode);
  const exchangeSelected = useGameStore((s) => s.exchangeSelected);
  const setExchangeMode = useGameStore((s) => s.setExchangeMode);
  const aiThinking = useGameStore((s) => s.aiThinking);

  const isDisabled = disabled || aiThinking;
  const hasPending = pendingTiles.length > 0;

  const buttonBase =
    "rounded-full px-4 py-2.5 transition-all duration-200 active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed touch-manipulation";

  if (exchangeMode) {
    return (
      <>
        <div className="order-2 flex flex-wrap items-center justify-center gap-2 lg:order-1">
          <button
            onClick={onExchange}
            disabled={exchangeSelected.size === 0}
            className={`${buttonBase} border border-amber-300/22 bg-[linear-gradient(135deg,rgba(251,191,36,0.15),rgba(112,66,10,0.08))] shadow-[0_14px_30px_rgba(251,191,36,0.08)] hover:border-amber-200/38 hover:bg-[linear-gradient(135deg,rgba(251,191,36,0.20),rgba(133,76,11,0.11))]`}
          >
            <span className="font-gold-shiny text-[1.38rem] font-black leading-none sm:text-[1.46rem]">
              Confirm exchange
            </span>
          </button>
          <button
            onClick={() => setExchangeMode(false)}
            className={`${buttonBase} border border-white/12 bg-white/6 shadow-[0_14px_30px_rgba(0,0,0,0.18)] hover:border-white/20 hover:bg-white/8`}
          >
            <span className="font-gold-shiny text-[1.34rem] font-black leading-none sm:text-[1.42rem]">
              Cancel
            </span>
          </button>
        </div>

        <div className="order-3 w-full text-center text-sm uppercase tracking-[0.16em] text-stone-400 lg:order-4">
          {exchangeSelected.size} tile{exchangeSelected.size !== 1 ? "s" : ""} selected
        </div>
      </>
    );
  }

  return (
    <>
      <div className="order-2 flex flex-wrap items-center justify-center gap-2 lg:order-1 lg:justify-start">
        <button
          onClick={() => setExchangeMode(true)}
          disabled={isDisabled || hasPending}
          className={`${buttonBase} border border-amber-300/22 bg-[linear-gradient(135deg,rgba(251,191,36,0.15),rgba(112,66,10,0.08))] shadow-[0_14px_30px_rgba(251,191,36,0.08)] hover:border-amber-200/38 hover:bg-[linear-gradient(135deg,rgba(251,191,36,0.20),rgba(133,76,11,0.11))]`}
        >
          <span className="font-gold-shiny text-[1.4rem] font-black leading-none sm:text-[1.48rem]">
            Exchange
          </span>
        </button>
        <button
          onClick={onPass}
          disabled={isDisabled || hasPending}
          className={`${buttonBase} border border-white/12 bg-white/6 shadow-[0_14px_30px_rgba(0,0,0,0.18)] hover:border-white/20 hover:bg-white/8`}
        >
          <span className="font-gold-shiny text-[1.4rem] font-black leading-none sm:text-[1.48rem]">
            Pass
          </span>
        </button>
      </div>

      <div className="order-3 flex justify-center lg:order-3 lg:justify-end">
        <div className="rounded-full border border-emerald-900/70 bg-[linear-gradient(180deg,rgba(6,24,19,0.94),rgba(4,18,14,0.98))] p-1.5 shadow-[0_22px_48px_rgba(4,120,87,0.16)] backdrop-blur-sm">
          <button
            onClick={onPlay}
            disabled={isDisabled || !hasPending}
            className={`${buttonBase} min-w-[124px] border border-emerald-800/80 bg-[linear-gradient(135deg,rgba(7,69,52,0.86),rgba(5,48,37,0.96))] px-5 shadow-[0_14px_32px_rgba(4,120,87,0.20)] hover:border-emerald-700/90 hover:bg-[linear-gradient(135deg,rgba(9,88,67,0.9),rgba(5,56,42,0.98))]`}
          >
            <span className="font-gold-shiny text-[1.44rem] font-black leading-none sm:text-[1.52rem]">
              Play
            </span>
          </button>
        </div>
      </div>
    </>
  );
}
