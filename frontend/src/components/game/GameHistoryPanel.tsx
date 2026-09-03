"use client";

import { motion } from "framer-motion";
import { useMemo } from "react";
import { useGameStore } from "@/hooks/useGameStore";
import {
  t as translate,
  useLocale,
  useT,
  type Locale,
  type TextKey,
} from "@/lib/i18n";
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
  GameHistorySort,
} from "@/lib/types";

const FILTER_OPTIONS: Array<{
  value: GameHistoryFilter;
  labelKey: TextKey;
  emoji: string;
}> = [
  { value: "vs_ai", labelKey: "history.filter.ai", emoji: "🤖" },
  { value: "vs_human", labelKey: "history.filter.human", emoji: "🤝" },
  { value: "all", labelKey: "history.filter.all", emoji: "🗂️" },
];

const OUTCOME_META: Record<
  GameHistoryOutcome,
  { emoji: string; labelKey: TextKey; className: string }
> = {
  waiting: {
    emoji: "⏳",
    labelKey: "history.outcome.waiting",
    className: "border-sky-300/18 bg-sky-400/10 text-sky-100",
  },
  in_progress: {
    emoji: "🎮",
    labelKey: "history.outcome.active",
    className: "border-emerald-300/18 bg-emerald-400/10 text-emerald-100",
  },
  won: {
    emoji: "🏆",
    labelKey: "history.outcome.won",
    className: "border-amber-300/20 bg-amber-300/12 text-amber-100",
  },
  lost: {
    emoji: "📉",
    labelKey: "history.outcome.lost",
    className: "border-white/10 bg-white/6 text-stone-200",
  },
  draw: {
    emoji: "🤝",
    labelKey: "history.outcome.draw",
    className: "border-sky-300/18 bg-sky-400/10 text-sky-100",
  },
  gave_up: {
    emoji: "🚪",
    labelKey: "history.outcome.gaveUp",
    className: "border-rose-300/20 bg-rose-500/10 text-rose-100",
  },
  abandoned: {
    emoji: "🪫",
    labelKey: "history.outcome.abandoned",
    className: "border-stone-400/14 bg-stone-400/10 text-stone-200",
  },
};

export const GAME_END_REASON_KEYS: Record<string, TextKey> = {
  BAG_EMPTY_AND_PLAYER_OUT: "history.endReason.bagEmpty",
  NO_MOVES_AVAILABLE: "history.endReason.noMoves",
  SIX_CONSECUTIVE_ZERO_SCORES: "history.endReason.sixZero",
  give_up: "history.endReason.gaveUp",
  queue_cancelled: "history.endReason.queueCancelled",
};

function historyEndReasonText(
  reason: string,
  translateKey: (key: TextKey) => string,
): string {
  if (!reason) return translateKey("history.hint.boardReady");
  const key = GAME_END_REASON_KEYS[reason];
  return key ? translateKey(key) : reason;
}

export function formatUpdatedAt(value: string, locale: Locale): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return translate(locale, "history.unknownDate");
  }
  return new Intl.DateTimeFormat(locale === "en" ? "en-US" : locale, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function OutcomeBadge({ outcome }: { outcome: GameHistoryOutcome }) {
  const { t } = useT();
  const meta = OUTCOME_META[outcome];
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[0.78rem] font-semibold leading-none shadow-[0_10px_24px_rgba(0,0,0,0.14)] ${meta.className}`}
    >
      <span className="text-[0.92rem] leading-none" aria-hidden="true">{meta.emoji}</span>
      <span>{t(meta.labelKey)}</span>
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
  const { t } = useT();
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
        {current ? t("history.current") : t("history.open")}
      </span>
    </button>
  );
}

export function GameHistoryPanel({
  data,
  filter,
  sort,
  loading,
  error,
  activeGameId,
  onFilterChange,
  onPrevPage,
  onNextPage,
  onRefresh,
  onSortChange,
  onOpenGame,
  className,
}: {
  data: GameHistoryResponse | null;
  filter: GameHistoryFilter;
  sort: GameHistorySort;
  loading: boolean;
  error: string | null;
  activeGameId?: string;
  onFilterChange: (value: GameHistoryFilter) => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  onRefresh: () => void;
  onSortChange: (value: GameHistorySort) => void;
  onOpenGame: (item: GameHistoryItem) => void;
  className?: string;
}) {
  const locale = useLocale();
  const { t, tf } = useT();
  const premiumLookEnabled = useGameStore((s) => s.premiumLookEnabled);
  const premiumTitleClass = premiumLookEnabled ? PREMIUM_GOLD_TEXT_SHADOW_CLASS : "";

  const pageSummary = useMemo(() => {
    if (!data || data.total === 0) return t("history.noneYet");
    const from = (data.page - 1) * data.page_size + 1;
    const to = Math.min(data.total, from + data.items.length - 1);
    return tf("history.showing", { from, to, total: data.total });
  }, [data, t, tf]);

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
                {t(option.labelKey)}
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
            {t("history.refresh")}
          </span>
        </button>
        <div className="flex items-center gap-2 rounded-full border border-white/8 bg-black/18 px-2 py-1 shadow-[0_10px_22px_rgba(0,0,0,0.12)]">
          {[
            { value: "updated", labelKey: "history.sort.recent" as const },
          ].map((option) => {
            const active = sort === option.value;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => onSortChange(option.value as GameHistorySort)}
                className={`rounded-full px-3 py-1.5 text-[0.78rem] font-semibold transition-colors ${
                  active
                    ? "bg-amber-400/12 text-amber-100"
                    : "text-stone-400 hover:text-stone-200"
                }`}
              >
                {t(option.labelKey)}
              </button>
            );
          })}
        </div>
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
              {t("history.loading")}
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
              {t("history.empty.title")}
            </div>
            <div className="mt-2 text-sm text-stone-300">
              {t("history.empty.body")}
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
                  <th className="px-4 py-3">{t("history.col.rival")}</th>
                  <th className="px-4 py-3">{t("history.col.mode")}</th>
                  <th className="px-4 py-3">{t("history.col.result")}</th>
                  <th className="px-4 py-3">{t("history.col.score")}</th>
                  <th className="px-4 py-3">{t("history.col.moves")}</th>
                  <th className="px-4 py-3">{t("history.col.updated")}</th>
                  <th className="px-4 py-3 text-right">{t("history.open")}</th>
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
                        {item.is_my_turn
                          ? t("game.status.yourTurn")
                          : item.status === "waiting"
                            ? t("history.hint.waitingRoom")
                            : historyEndReasonText(item.game_end_reason, t)}
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-sm text-stone-200">
                      {t(
                        item.game_mode === "vs_ai"
                          ? "history.mode.ai"
                          : "history.mode.human",
                      )}
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
                      {formatUpdatedAt(item.updated_at, locale)}
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
                      {t(
                        item.game_mode === "vs_ai"
                          ? "history.mode.ai"
                          : "history.mode.human",
                      )}
                    </div>
                  </div>
                  <OutcomeBadge outcome={item.outcome} />
                </div>

                <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="text-[0.68rem] uppercase tracking-[0.2em] text-stone-500">
                      {t("history.col.score")}
                    </div>
                    <div className="mt-1 font-gold-shiny text-[1.08rem] font-black leading-none">
                      {item.my_score}
                      <span className="px-1 text-white/56">:</span>
                      {item.opponent_score}
                    </div>
                  </div>
                  <div>
                    <div className="text-[0.68rem] uppercase tracking-[0.2em] text-stone-500">
                      {t("history.col.moves")}
                    </div>
                    <div className="mt-1 text-stone-200">{item.move_count}</div>
                  </div>
                </div>

                <div className="mt-2 text-sm text-stone-400">
                  {formatUpdatedAt(item.updated_at, locale)}
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
          {data
            ? tf("history.pageOf", { page: data.page, total: data.total_pages })
            : tf("history.pageOf", { page: 1, total: 1 })}
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
              {t("history.prev")}
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
              {t("history.next")}
            </span>
          </motion.button>
        </div>
      </div>
    </div>
  );
}
