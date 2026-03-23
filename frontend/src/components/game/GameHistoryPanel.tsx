"use client";

import { motion } from "framer-motion";
import { useMemo } from "react";
import { useGameStore } from "@/hooks/useGameStore";
import {
  PREMIUM_GOLD_TEXT_SHADOW_CLASS,
  PREMIUM_MODAL_CARD_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";
import type {
  GameHistoryFilter,
  GameHistoryItem,
  GameHistoryOutcome,
  GameHistoryResponse,
} from "@/lib/types";

const FILTER_OPTIONS: Array<{
  value: GameHistoryFilter;
  label: string;
  emoji: string;
}> = [
  { value: "vs_ai", label: "AI", emoji: "🤖" },
  { value: "vs_human", label: "Human", emoji: "🤝" },
  { value: "all", label: "All", emoji: "🗂️" },
];

const OUTCOME_META: Record<
  GameHistoryOutcome,
  { emoji: string; label: string; className: string }
> = {
  waiting: {
    emoji: "⏳",
    label: "Waiting",
    className: "border-sky-300/18 bg-sky-400/10 text-sky-100",
  },
  in_progress: {
    emoji: "🎮",
    label: "In progress",
    className: "border-emerald-300/18 bg-emerald-400/10 text-emerald-100",
  },
  won: {
    emoji: "🏆",
    label: "Won",
    className: "border-amber-300/20 bg-amber-300/12 text-amber-100",
  },
  lost: {
    emoji: "📉",
    label: "Lost",
    className: "border-white/10 bg-white/6 text-stone-200",
  },
  gave_up: {
    emoji: "🚪",
    label: "Gave up",
    className: "border-rose-300/20 bg-rose-500/10 text-rose-100",
  },
  abandoned: {
    emoji: "🪫",
    label: "Abandoned",
    className: "border-stone-400/14 bg-stone-400/10 text-stone-200",
  },
};

function formatUpdatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatMode(mode: GameHistoryItem["game_mode"]): string {
  return mode === "vs_ai" ? "AI duel" : "Human duel";
}

function OutcomeBadge({ outcome }: { outcome: GameHistoryOutcome }) {
  const meta = OUTCOME_META[outcome];
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[0.78rem] font-semibold leading-none shadow-[0_10px_24px_rgba(0,0,0,0.14)] ${meta.className}`}
    >
      <span className="text-[0.92rem] leading-none" aria-hidden="true">{meta.emoji}</span>
      <span>{meta.label}</span>
    </span>
  );
}

function OpenButton({
  onClick,
  current,
}: {
  onClick: () => void;
  current: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group inline-flex h-[2.2rem] items-center justify-center rounded-full border px-4 py-2 shadow-[0_10px_24px_rgba(0,0,0,0.16)] transition-all duration-200 active:scale-[0.98] ${
        current
          ? "border-white/14 bg-white/6"
          : "border-amber-200/34 bg-[linear-gradient(135deg,rgba(251,191,36,0.16),rgba(245,158,11,0.08))] hover:border-white/44 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.18),rgba(251,191,36,0.18),rgba(245,158,11,0.12))]"
      }`}
    >
      <span className={`font-gold-shiny text-[0.95rem] font-black leading-none ${PREMIUM_GOLD_TEXT_SHADOW_CLASS}`}>
        {current ? "Current" : "Open"}
      </span>
    </button>
  );
}

export function GameHistoryPanel({
  data,
  filter,
  loading,
  error,
  activeGameId,
  onFilterChange,
  onPrevPage,
  onNextPage,
  onRefresh,
  onOpenGame,
  className,
}: {
  data: GameHistoryResponse | null;
  filter: GameHistoryFilter;
  loading: boolean;
  error: string | null;
  activeGameId?: string;
  onFilterChange: (value: GameHistoryFilter) => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  onRefresh: () => void;
  onOpenGame: (item: GameHistoryItem) => void;
  className?: string;
}) {
  const premiumLookEnabled = useGameStore((s) => s.premiumLookEnabled);
  const premiumTitleClass = premiumLookEnabled ? PREMIUM_GOLD_TEXT_SHADOW_CLASS : "";

  const pageSummary = useMemo(() => {
    if (!data || data.total === 0) return "No saved boards yet";
    const from = (data.page - 1) * data.page_size + 1;
    const to = Math.min(data.total, from + data.items.length - 1);
    return `Showing ${from}-${to} of ${data.total} games`;
  }, [data]);

  return (
    <div className={`relative overflow-hidden rounded-[1.8rem] border border-white/8 bg-[linear-gradient(180deg,rgba(17,14,11,0.76),rgba(11,9,8,0.82))] p-3 shadow-[0_18px_45px_rgba(0,0,0,0.24)] sm:p-4 ${className ?? ""}`}
      style={premiumLookEnabled ? PREMIUM_MODAL_CARD_STYLE : undefined}
      onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
    >
      <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/12 to-transparent" />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {FILTER_OPTIONS.map((option) => {
          const active = filter === option.value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onFilterChange(option.value)}
              className={`group inline-flex h-[2.35rem] items-center gap-2 rounded-full border px-3.5 py-2 transition-all duration-200 active:scale-[0.98] ${
                active
                  ? "border-amber-200/38 bg-[linear-gradient(135deg,rgba(251,191,36,0.16),rgba(245,158,11,0.08))] shadow-[0_12px_26px_rgba(251,191,36,0.08)]"
                  : "border-white/10 bg-white/[0.04] hover:border-white/18 hover:bg-white/[0.07]"
              }`}
            >
              <span className="text-[1rem] leading-none" aria-hidden="true">{option.emoji}</span>
              <span className={`font-gold-shiny text-[0.98rem] font-black leading-none ${premiumTitleClass}`}>
                {option.label}
              </span>
            </button>
          );
        })}
        <button
          type="button"
          onClick={onRefresh}
          className="ml-auto group inline-flex h-[2.35rem] items-center gap-2 rounded-full border border-amber-300/24 bg-[linear-gradient(135deg,rgba(251,191,36,0.10),rgba(255,255,255,0.04))] px-3.5 py-2 shadow-[0_10px_22px_rgba(0,0,0,0.14)] transition-all duration-200 hover:border-white/42 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.14),rgba(251,191,36,0.14),rgba(245,158,11,0.08))]"
        >
          <span className={`font-gold-shiny text-[0.96rem] font-black leading-none ${premiumTitleClass}`}>
            Refresh
          </span>
        </button>
      </div>

      <div className="mb-4 text-xs uppercase tracking-[0.18em] text-stone-400">
        {pageSummary}
      </div>

      {error ? (
        <div className="rounded-[1.2rem] border border-rose-300/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100 shadow-[0_14px_32px_rgba(0,0,0,0.16)]">
          {error}
        </div>
      ) : null}

      {!error && loading ? (
        <div className="flex min-h-[240px] items-center justify-center">
          <div className="text-center">
            <div className="text-[2rem] leading-none">⌛</div>
            <div className="mt-3 font-gold-shiny text-[1.16rem] font-black">
              Loading games
            </div>
          </div>
        </div>
      ) : null}

      {!error && !loading && data?.items.length === 0 ? (
        <div className="flex min-h-[240px] items-center justify-center">
          <div className="max-w-md text-center">
            <div className="text-[2rem] leading-none">
              {filter === "vs_human" ? "🤝" : filter === "all" ? "🗂️" : "🧠"}
            </div>
            <div className="mt-3 font-gold-shiny text-[1.2rem] font-black">
              No games in this filter yet
            </div>
            <div className="mt-2 text-sm text-stone-300">
              Start a new board and it will show up here with premium paging, result badges, and quick resume links.
            </div>
          </div>
        </div>
      ) : null}

      {!error && !loading && data && data.items.length > 0 ? (
        <>
          <div className="hidden overflow-hidden rounded-[1.2rem] border border-white/8 md:block">
            <table className="min-w-full divide-y divide-white/8">
              <thead className="bg-white/[0.04]">
                <tr className="text-left text-[0.72rem] uppercase tracking-[0.22em] text-stone-400">
                  <th className="px-4 py-3">Rival</th>
                  <th className="px-4 py-3">Mode</th>
                  <th className="px-4 py-3">Result</th>
                  <th className="px-4 py-3">Score</th>
                  <th className="px-4 py-3">Moves</th>
                  <th className="px-4 py-3">Updated</th>
                  <th className="px-4 py-3 text-right">Open</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/6">
                {data.items.map((item) => (
                  <tr key={item.game_id} className="bg-black/10 transition-colors duration-200 hover:bg-white/[0.04]">
                    <td className="px-4 py-3.5">
                      <div className="font-gold-shiny text-[1.04rem] font-black leading-none">
                        {item.opponent_label}
                      </div>
                      <div className="mt-1 text-xs text-stone-400">
                        {item.is_my_turn ? "Your turn" : item.status === "waiting" ? "Waiting room" : item.game_end_reason || "Board ready"}
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-sm text-stone-200">
                      {formatMode(item.game_mode)}
                    </td>
                    <td className="px-4 py-3.5">
                      <OutcomeBadge outcome={item.outcome} />
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="font-gold-shiny text-[1.08rem] font-black leading-none">
                        {item.my_score}
                        <span className="px-1.5 text-white/56">:</span>
                        {item.opponent_score}
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-sm text-stone-200">
                      {item.move_count}
                    </td>
                    <td className="px-4 py-3.5 text-sm text-stone-300">
                      {formatUpdatedAt(item.updated_at)}
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <OpenButton
                        current={item.game_id === activeGameId}
                        onClick={() => onOpenGame(item)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid gap-3 md:hidden">
            {data.items.map((item) => (
              <div
                key={item.game_id}
                className="rounded-[1.3rem] border border-white/8 bg-black/18 px-4 py-3 shadow-[0_14px_32px_rgba(0,0,0,0.18)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-gold-shiny text-[1.08rem] font-black leading-none">
                      {item.opponent_label}
                    </div>
                    <div className="mt-1 text-xs uppercase tracking-[0.18em] text-stone-400">
                      {formatMode(item.game_mode)}
                    </div>
                  </div>
                  <OutcomeBadge outcome={item.outcome} />
                </div>

                <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <div className="text-[0.68rem] uppercase tracking-[0.2em] text-stone-500">Score</div>
                    <div className="mt-1 font-gold-shiny text-[1.08rem] font-black leading-none">
                      {item.my_score}
                      <span className="px-1 text-white/56">:</span>
                      {item.opponent_score}
                    </div>
                  </div>
                  <div>
                    <div className="text-[0.68rem] uppercase tracking-[0.2em] text-stone-500">Moves</div>
                    <div className="mt-1 text-stone-200">{item.move_count}</div>
                  </div>
                  <div>
                    <div className="text-[0.68rem] uppercase tracking-[0.2em] text-stone-500">Updated</div>
                    <div className="mt-1 text-stone-200">{formatUpdatedAt(item.updated_at)}</div>
                  </div>
                </div>

                <div className="mt-3 flex justify-end">
                  <OpenButton
                    current={item.game_id === activeGameId}
                    onClick={() => onOpenGame(item)}
                  />
                </div>
              </div>
            ))}
          </div>
        </>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/8 pt-4">
        <div className="text-sm text-stone-300">
          {data ? `Page ${data.page} of ${data.total_pages}` : "Page 1"}
        </div>
        <div className="flex items-center gap-2">
          <motion.button
            type="button"
            whileHover={{ y: -1.5 }}
            whileTap={{ scale: 0.985 }}
            onClick={onPrevPage}
            disabled={!data?.has_previous || loading}
            className="rounded-full border border-white/10 bg-white/6 px-4 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-white/18 hover:bg-white/8 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span className={`font-gold-shiny text-[1rem] font-black leading-none ${premiumTitleClass}`}>
              Previous
            </span>
          </motion.button>
          <motion.button
            type="button"
            whileHover={{ y: -1.5 }}
            whileTap={{ scale: 0.985 }}
            onClick={onNextPage}
            disabled={!data?.has_next || loading}
            className="rounded-full border border-amber-300/26 bg-[linear-gradient(135deg,rgba(251,191,36,0.12),rgba(255,255,255,0.04))] px-4 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18),0_0_24px_rgba(251,191,36,0.08)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-amber-200/50 hover:bg-[linear-gradient(135deg,rgba(251,191,36,0.18),rgba(255,255,255,0.06))] hover:shadow-[0_14px_30px_rgba(0,0,0,0.24),0_0_30px_rgba(251,191,36,0.14)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span className={`font-gold-shiny text-[1rem] font-black leading-none ${premiumTitleClass}`}>
              Next
            </span>
          </motion.button>
        </div>
      </div>
    </div>
  );
}
