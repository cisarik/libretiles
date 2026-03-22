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
    "inline-flex h-[2.85rem] items-center justify-center whitespace-nowrap rounded-full px-3 py-2 text-center transition-all duration-200 active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed touch-manipulation sm:h-auto sm:px-4 sm:py-2.5";
  const actionButtonBase =
    "group min-w-0 border shadow-[0_14px_30px_rgba(0,0,0,0.18)] sm:flex-none";
  const playShell =
    "rounded-full border border-emerald-500/36 bg-[linear-gradient(180deg,rgba(8,20,16,0.98),rgba(2,8,6,0.98))] p-1 shadow-[0_0_0_1px_rgba(16,185,129,0.08),0_18px_42px_rgba(0,0,0,0.48),0_0_28px_rgba(16,185,129,0.18)] backdrop-blur-sm transition-all duration-200 hover:border-white/34 hover:shadow-[0_0_0_1px_rgba(16,185,129,0.12),0_18px_44px_rgba(0,0,0,0.52),0_0_32px_rgba(16,185,129,0.24)]";
  const playButton =
    `${buttonBase} group min-w-0 border border-emerald-300/52 bg-[linear-gradient(135deg,rgba(16,168,110,0.98),rgba(8,112,74,1))] px-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.14),0_12px_28px_rgba(0,0,0,0.34),0_0_20px_rgba(16,185,129,0.18)] hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(28,191,128,1),rgba(11,128,85,1))] hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_14px_34px_rgba(0,0,0,0.38),0_0_26px_rgba(16,185,129,0.22)]`;

  if (exchangeMode) {
    return (
      <>
        <div className="order-2 grid w-full grid-cols-2 gap-2 lg:hidden">
          <button
            onClick={onExchange}
            disabled={exchangeSelected.size === 0}
            className={`${buttonBase} ${actionButtonBase} border-amber-300/22 bg-[linear-gradient(135deg,rgba(251,191,36,0.15),rgba(112,66,10,0.08))] shadow-[0_14px_30px_rgba(251,191,36,0.08)] hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.16),rgba(251,191,36,0.16),rgba(133,76,11,0.12))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.05)]`}
          >
            <LuxeHoverText className="text-[1rem] font-black leading-none sm:text-[1.42rem]">
              Confirm exchange
            </LuxeHoverText>
          </button>
          <button
            onClick={() => setExchangeMode(false)}
            className={`${buttonBase} ${actionButtonBase} border-white/12 bg-white/6 hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,255,255,0.12),rgba(255,255,255,0.06))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.04)]`}
          >
            <LuxeHoverText className="text-[1rem] font-black leading-none sm:text-[1.42rem]">
              Cancel
            </LuxeHoverText>
          </button>
        </div>

        <div className="hidden lg:flex lg:col-start-1 lg:row-start-1 lg:order-1 lg:items-center lg:gap-2">
          <button
            onClick={onExchange}
            disabled={exchangeSelected.size === 0}
            className={`${buttonBase} ${actionButtonBase} border-amber-300/22 bg-[linear-gradient(135deg,rgba(251,191,36,0.15),rgba(112,66,10,0.08))] shadow-[0_14px_30px_rgba(251,191,36,0.08)] hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.16),rgba(251,191,36,0.16),rgba(133,76,11,0.12))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.05)]`}
          >
            <LuxeHoverText className="text-[1.38rem] font-black leading-none sm:text-[1.46rem]">
              Confirm exchange
            </LuxeHoverText>
          </button>
          <button
            onClick={() => setExchangeMode(false)}
            className={`${buttonBase} ${actionButtonBase} border-white/12 bg-white/6 hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,255,255,0.12),rgba(255,255,255,0.06))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.04)]`}
          >
            <LuxeHoverText className="text-[1.34rem] font-black leading-none sm:text-[1.42rem]">
              Cancel
            </LuxeHoverText>
          </button>
        </div>

        <div className="order-3 w-full text-center text-sm uppercase tracking-[0.16em] text-stone-400 lg:col-start-2 lg:row-start-2 lg:order-2 lg:self-center">
          {exchangeSelected.size} tile{exchangeSelected.size !== 1 ? "s" : ""} selected
        </div>
      </>
    );
  }

  return (
    <>
      <div className="order-2 grid w-full grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.08fr)] items-center gap-2 lg:hidden">
        <button
          onClick={() => setExchangeMode(true)}
          disabled={isDisabled || hasPending}
          className={`${buttonBase} ${actionButtonBase} w-full border-amber-300/22 bg-[linear-gradient(135deg,rgba(251,191,36,0.15),rgba(112,66,10,0.08))] shadow-[0_14px_30px_rgba(251,191,36,0.08)] hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.16),rgba(251,191,36,0.16),rgba(133,76,11,0.12))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.05)]`}
        >
          <LuxeHoverText className="text-[1.1rem] font-black leading-none sm:text-[1.48rem]">
            Exchange
          </LuxeHoverText>
        </button>
        <button
          onClick={onPass}
          disabled={isDisabled || hasPending}
          className={`${buttonBase} ${actionButtonBase} w-full border-white/12 bg-white/6 hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,255,255,0.12),rgba(255,255,255,0.06))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.04)]`}
        >
          <LuxeHoverText className="text-[1.1rem] font-black leading-none sm:text-[1.48rem]">
            Pass
          </LuxeHoverText>
        </button>
        <div className={playShell}>
          <button
            onClick={onPlay}
            disabled={isDisabled || !hasPending}
            className={`${playButton} w-full min-w-[5.3rem]`}
          >
            <LuxeHoverText className="text-[1.12rem] font-black leading-none sm:text-[1.52rem]">
              Play
            </LuxeHoverText>
          </button>
        </div>
      </div>

      <div className="hidden lg:flex lg:col-start-1 lg:row-start-1 lg:order-1 lg:items-center lg:gap-2">
        <button
          onClick={() => setExchangeMode(true)}
          disabled={isDisabled || hasPending}
          className={`${buttonBase} ${actionButtonBase} border-amber-300/22 bg-[linear-gradient(135deg,rgba(251,191,36,0.15),rgba(112,66,10,0.08))] shadow-[0_14px_30px_rgba(251,191,36,0.08)] hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.16),rgba(251,191,36,0.16),rgba(133,76,11,0.12))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.05)]`}
        >
          <LuxeHoverText className="text-[1.18rem] font-black leading-none sm:text-[1.48rem]">
            Exchange
          </LuxeHoverText>
        </button>
        <button
          onClick={onPass}
          disabled={isDisabled || hasPending}
          className={`${buttonBase} ${actionButtonBase} border-white/12 bg-white/6 hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,255,255,0.12),rgba(255,255,255,0.06))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.04)]`}
        >
          <LuxeHoverText className="text-[1.18rem] font-black leading-none sm:text-[1.48rem]">
            Pass
          </LuxeHoverText>
        </button>
      </div>

      <div className="hidden lg:flex lg:col-start-3 lg:row-start-1 lg:order-3 lg:justify-self-end">
        <div className={playShell}>
          <button
            onClick={onPlay}
            disabled={isDisabled || !hasPending}
            className={`${playButton} min-w-[6.1rem]`}
          >
            <LuxeHoverText className="text-[1.34rem] font-black leading-none sm:text-[1.52rem]">
              Play
            </LuxeHoverText>
          </button>
        </div>
      </div>
    </>
  );
}
