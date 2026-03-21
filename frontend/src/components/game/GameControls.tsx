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
    "min-w-[92px] px-5 py-3 rounded-[1rem] font-semibold text-sm transition-all duration-200 " +
    "shadow-[0_16px_32px_rgba(0,0,0,0.22)] active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed touch-manipulation ";

  if (exchangeMode) {
    return (
      <div className="flex flex-wrap items-center justify-center gap-3">
        <span className="text-stone-400 text-sm">
          {exchangeSelected.size} tile{exchangeSelected.size !== 1 ? "s" : ""} selected
        </span>
        <button
          onClick={onExchange}
          disabled={exchangeSelected.size === 0}
          className={buttonBase + "bg-sky-600 hover:bg-sky-500 text-white shadow-sky-600/30"}
        >
          Confirm Exchange
        </button>
        <button
          onClick={() => setExchangeMode(false)}
          className={buttonBase + "bg-stone-700 hover:bg-stone-600 text-stone-200"}
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[940px] flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex justify-center sm:justify-start">
        <div className="rounded-[1.25rem] border border-white/8 bg-stone-900/70 p-2 shadow-[0_18px_42px_rgba(0,0,0,0.24)] backdrop-blur-sm">
          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setExchangeMode(true)}
              disabled={isDisabled || hasPending}
              className={buttonBase + "bg-sky-600 hover:bg-sky-500 text-white shadow-sky-600/30"}
            >
              Exchange
            </button>
            <button
              onClick={onPass}
              disabled={isDisabled || hasPending}
              className={buttonBase + "bg-stone-700 hover:bg-stone-600 text-stone-200 shadow-stone-700/30"}
            >
              Pass
            </button>
          </div>
        </div>
      </div>

      <div className="flex justify-center sm:justify-end">
        <div className="rounded-[1.35rem] border border-emerald-300/20 bg-emerald-500/10 p-2 shadow-[0_22px_48px_rgba(5,150,105,0.14)] backdrop-blur-sm">
          <button
            onClick={onPlay}
            disabled={isDisabled || !hasPending}
            className={buttonBase + "min-w-[124px] bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/30"}
          >
            Play
          </button>
        </div>
      </div>
    </div>
  );
}
