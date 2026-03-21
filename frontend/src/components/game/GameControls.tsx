"use client";

import { useGameStore } from "@/hooks/useGameStore";

interface GameControlsProps {
  onPlay: () => void;
  onExchange: () => void;
  onPass: () => void;
  disabled?: boolean;
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

export function GameControls({ onPlay, onExchange, onPass, disabled }: GameControlsProps) {
  const pendingTiles = useGameStore((s) => s.pendingTiles);
  const exchangeMode = useGameStore((s) => s.exchangeMode);
  const exchangeSelected = useGameStore((s) => s.exchangeSelected);
  const setExchangeMode = useGameStore((s) => s.setExchangeMode);
  const aiThinking = useGameStore((s) => s.aiThinking);

  const isDisabled = disabled || aiThinking;
  const hasPending = pendingTiles.length > 0;

  const buttonBase =
    "inline-flex items-center justify-center whitespace-nowrap rounded-full px-4 py-2.5 text-center transition-all duration-200 active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed touch-manipulation";

  if (exchangeMode) {
    return (
      <>
        <div className="order-2 flex flex-wrap items-center justify-center gap-2 lg:order-1">
          <button
            onClick={onExchange}
            disabled={exchangeSelected.size === 0}
            className={`${buttonBase} group border border-amber-300/22 bg-[linear-gradient(135deg,rgba(251,191,36,0.15),rgba(112,66,10,0.08))] shadow-[0_14px_30px_rgba(251,191,36,0.08)] hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.16),rgba(251,191,36,0.16),rgba(133,76,11,0.12))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.05)]`}
          >
            <LuxeHoverText className="text-[1.38rem] font-black leading-none sm:text-[1.46rem]">
              Confirm exchange
            </LuxeHoverText>
          </button>
          <button
            onClick={() => setExchangeMode(false)}
            className={`${buttonBase} group border border-white/12 bg-white/6 shadow-[0_14px_30px_rgba(0,0,0,0.18)] hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,255,255,0.12),rgba(255,255,255,0.06))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.04)]`}
          >
            <LuxeHoverText className="text-[1.34rem] font-black leading-none sm:text-[1.42rem]">
              Cancel
            </LuxeHoverText>
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
          className={`${buttonBase} group border border-amber-300/22 bg-[linear-gradient(135deg,rgba(251,191,36,0.15),rgba(112,66,10,0.08))] shadow-[0_14px_30px_rgba(251,191,36,0.08)] hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.16),rgba(251,191,36,0.16),rgba(133,76,11,0.12))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.05)]`}
        >
          <LuxeHoverText className="text-[1.4rem] font-black leading-none sm:text-[1.48rem]">
            Exchange
          </LuxeHoverText>
        </button>
        <button
          onClick={onPass}
          disabled={isDisabled || hasPending}
          className={`${buttonBase} group border border-white/12 bg-white/6 shadow-[0_14px_30px_rgba(0,0,0,0.18)] hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,255,255,0.12),rgba(255,255,255,0.06))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.04)]`}
        >
          <LuxeHoverText className="text-[1.4rem] font-black leading-none sm:text-[1.48rem]">
            Pass
          </LuxeHoverText>
        </button>
      </div>

      <div className="order-3 flex justify-center lg:order-3 lg:justify-end">
        <div className="rounded-full border border-emerald-900/70 bg-[linear-gradient(180deg,rgba(6,24,19,0.94),rgba(4,18,14,0.98))] p-1.5 shadow-[0_22px_48px_rgba(4,120,87,0.16)] backdrop-blur-sm transition-all duration-200 hover:border-white/28 hover:shadow-[0_22px_48px_rgba(4,120,87,0.16),0_0_24px_rgba(255,255,255,0.04)]">
          <button
            onClick={onPlay}
            disabled={isDisabled || !hasPending}
            className={`${buttonBase} group min-w-[124px] border border-emerald-800/80 bg-[linear-gradient(135deg,rgba(7,69,52,0.86),rgba(5,48,37,0.96))] px-5 shadow-[0_14px_32px_rgba(4,120,87,0.20)] hover:border-white/36 hover:bg-[linear-gradient(135deg,rgba(22,96,76,0.92),rgba(8,62,48,0.98))] hover:shadow-[0_16px_34px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.04)]`}
          >
            <LuxeHoverText className="text-[1.44rem] font-black leading-none sm:text-[1.52rem]">
              Play
            </LuxeHoverText>
          </button>
        </div>
      </div>
    </>
  );
}
