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
    "px-5 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 " +
    "shadow-lg active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed ";

  if (exchangeMode) {
    return (
      <div className="flex items-center gap-3">
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
    <div className="flex items-center gap-3">
      <button
        onClick={onPlay}
        disabled={isDisabled || !hasPending}
        className={buttonBase + "bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/30"}
      >
        Play
      </button>
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
  );
}
