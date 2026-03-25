"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";

import { GameHistoryPanel } from "@/components/game/GameHistoryPanel";
import { useGameStore } from "@/hooks/useGameStore";
import { api } from "@/lib/api";
import {
  PREMIUM_GOLD_TEXT_SHADOW_CLASS,
  PREMIUM_HEADER_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";
import type {
  CreateGameResponse,
  GameHistoryFilter,
  GameHistoryItem,
  GameHistoryResponse,
  GameHistorySort,
  QueueJoinResponse,
} from "@/lib/types";

function humanizeModelId(modelId?: string | null): string {
  if (!modelId) return "Choose AI";
  const base = modelId.split("/").pop() ?? modelId;
  return base
    .split(/[-_]+/)
    .filter(Boolean)
    .map((part) => (/^[0-9.]+$/.test(part) ? part : part[0].toUpperCase() + part.slice(1)))
    .join(" ");
}

export default function PlayPage() {
  const router = useRouter();
  const token = useGameStore((state) => state.token);
  const selectedModelId = useGameStore((state) => state.selectedModelId);
  const selectedPromptId = useGameStore((state) => state.selectedPromptId);
  const premiumLookEnabled = useGameStore((state) => state.premiumLookEnabled);
  const setStartingDraw = useGameStore((state) => state.setStartingDraw);
  const setStartingRack = useGameStore((state) => state.setStartingRack);
  const setGameState = useGameStore((state) => state.setGameState);
  const resetGameUi = useGameStore((state) => state.resetGameUi);

  const [startingAI, setStartingAI] = useState(false);
  const [joiningHuman, setJoiningHuman] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyFilter, setHistoryFilter] = useState<GameHistoryFilter>("all");
  const [historySort, setHistorySort] = useState<GameHistorySort>("updated");
  const [historyData, setHistoryData] = useState<GameHistoryResponse | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const activeModelLabel = humanizeModelId(selectedModelId);
  const premiumTitleClass = premiumLookEnabled ? PREMIUM_GOLD_TEXT_SHADOW_CLASS : "";

  const fetchHistory = useCallback(async ({
    page = 1,
    filter = historyFilter,
    sort = historySort,
  }: {
    page?: number;
    filter?: GameHistoryFilter;
    sort?: GameHistorySort;
  } = {}) => {
    if (!token) return;

    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const result = await api.listGameHistory(token, {
        game_mode: filter,
        sort,
        page,
        page_size: 8,
      });
      setHistoryData(result);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : "Unable to load your games.");
    } finally {
      setHistoryLoading(false);
    }
  }, [historyFilter, historySort, token]);

  useEffect(() => {
    if (!token) {
      router.replace("/");
      return;
    }
    void fetchHistory({ page: 1 });
  }, [fetchHistory, router, token]);

  async function handleStartAI() {
    if (!token || startingAI) return;

    setStartingAI(true);
    setError(null);
    try {
      const result = (await api.createGame(token, {
        game_mode: "vs_ai",
        ai_model_model_id: selectedModelId || undefined,
        ai_prompt_id: selectedPromptId ?? undefined,
      })) as CreateGameResponse;
      resetGameUi();
      setStartingDraw(result.starting_draw);
      setStartingRack(result.human_rack);
      router.push(`/draw/${result.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start an AI game.");
    } finally {
      setStartingAI(false);
    }
  }

  async function handleJoinHuman() {
    if (!token || joiningHuman) return;

    setJoiningHuman(true);
    setError(null);
    try {
      const result = (await api.joinHumanQueue(token, { variant_slug: "english" })) as QueueJoinResponse;
      resetGameUi();
      setGameState(result.state);
      if (result.waiting) {
        router.push(`/waiting/${result.state.game_id}`);
        return;
      }
      router.push(`/game/${result.state.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not join the human queue.");
    } finally {
      setJoiningHuman(false);
    }
  }

  const handleHistoryFilterChange = useCallback((nextFilter: GameHistoryFilter) => {
    setHistoryFilter(nextFilter);
    void fetchHistory({ filter: nextFilter, sort: historySort, page: 1 });
  }, [fetchHistory, historySort]);

  const handleHistorySortChange = useCallback((nextSort: GameHistorySort) => {
    setHistorySort(nextSort);
    void fetchHistory({ filter: historyFilter, sort: nextSort, page: 1 });
  }, [fetchHistory, historyFilter]);

  const handleHistoryOpen = useCallback((item: GameHistoryItem) => {
    router.push(item.status === "waiting" ? `/waiting/${item.game_id}` : `/game/${item.game_id}`);
  }, [router]);

  const handleHistoryPrev = useCallback(() => {
    if (!historyData?.has_previous) return;
    void fetchHistory({ page: historyData.page - 1 });
  }, [fetchHistory, historyData]);

  const handleHistoryNext = useCallback(() => {
    if (!historyData?.has_next) return;
    void fetchHistory({ page: historyData.page + 1 });
  }, [fetchHistory, historyData]);

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(203,144,49,0.14),transparent_28%),linear-gradient(180deg,#0d0b09,#060505)] text-stone-100">
      <div className="mx-auto flex min-h-screen max-w-[1160px] flex-col justify-center px-4 py-6 sm:px-6">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
          className="mx-auto flex w-full max-w-[1020px] flex-col gap-5"
        >
          <div
            className={`relative overflow-hidden rounded-[2rem] border border-white/10 px-5 py-5 shadow-[0_26px_60px_rgba(0,0,0,0.32)] ${premiumLookEnabled ? "backdrop-blur-[14px]" : "bg-black/50"}`}
            style={premiumLookEnabled ? PREMIUM_HEADER_STYLE : undefined}
            onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
          >
            <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/58 to-transparent" />
            <div className="text-center">
              <div className="text-[0.78rem] uppercase tracking-[0.36em] text-stone-500">
                Libre Tiles
              </div>
              <h1 className="mt-3 text-4xl font-black tracking-tight text-stone-50 sm:text-5xl">
                Choose the next board
              </h1>
              <p className="mt-3 text-sm text-stone-400 sm:text-base">
                Start a premium AI duel, jump into the live queue, or reopen one of your saved boards.
              </p>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <button
              onClick={() => void handleStartAI()}
              disabled={startingAI || joiningHuman}
              className={`group relative overflow-hidden rounded-[2rem] border border-amber-300/20 p-7 text-left shadow-[0_26px_60px_rgba(0,0,0,0.32)] transition-all hover:border-white/40 hover:shadow-[0_30px_70px_rgba(255,255,255,0.06)] disabled:opacity-50 ${premiumLookEnabled ? "backdrop-blur-[14px]" : "bg-[linear-gradient(180deg,rgba(52,34,14,0.96),rgba(18,12,9,0.98))]"}`}
              style={premiumLookEnabled ? PREMIUM_HEADER_STYLE : undefined}
              onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
            >
              <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/54 to-transparent" />
              <div className="text-[0.72rem] uppercase tracking-[0.34em] text-amber-300/70">
                AI Match
              </div>
              <div className={`mt-4 font-gold-shiny text-3xl font-black leading-none text-stone-50 sm:text-[2.15rem] ${premiumTitleClass}`}>
                Play the house
              </div>
              <p className="mt-3 max-w-[28rem] text-sm text-stone-300">
                Use the current AI rival and keep the animated opening draw.
              </p>
              <div className="mt-6 inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-semibold text-stone-200">
                {startingAI ? "Preparing game..." : activeModelLabel}
              </div>
            </button>

            <button
              onClick={() => void handleJoinHuman()}
              disabled={joiningHuman || startingAI}
              className={`group relative overflow-hidden rounded-[2rem] border border-amber-300/16 p-7 text-left shadow-[0_26px_60px_rgba(0,0,0,0.32)] transition-all hover:border-white/40 hover:shadow-[0_30px_70px_rgba(255,255,255,0.06)] disabled:opacity-50 ${premiumLookEnabled ? "backdrop-blur-[14px]" : "bg-[linear-gradient(180deg,rgba(9,27,37,0.96),rgba(8,12,17,0.98))]"}`}
              style={premiumLookEnabled ? PREMIUM_HEADER_STYLE : undefined}
              onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
            >
              <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/54 to-transparent" />
              <div className="text-[0.72rem] uppercase tracking-[0.34em] text-stone-400">
                Human Queue
              </div>
              <div className={`mt-4 font-gold-shiny text-3xl font-black leading-none text-stone-50 sm:text-[2.15rem] ${premiumTitleClass}`}>
                Find a live opponent
              </div>
              <p className="mt-3 max-w-[28rem] text-sm text-stone-300">
                Join the first waiting player. If nobody is there, your board waits in the room.
              </p>
              <div className="mt-6 inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-semibold text-stone-200">
                {joiningHuman ? "Joining queue..." : "English queue"}
              </div>
            </button>
          </div>

          <div>
            <div className="mb-3 flex items-end justify-between gap-3">
              <div>
                <div className="text-[0.72rem] uppercase tracking-[0.28em] text-stone-500">
                  Saved boards
                </div>
                <div className={`mt-1 font-gold-shiny text-[1.65rem] font-black leading-none sm:text-[1.9rem] ${premiumTitleClass}`}>
                  Resume where you left off
                </div>
              </div>
              <div className="hidden text-right text-sm text-stone-400 md:block">
                AI and human games share one premium history surface.
              </div>
            </div>

            <GameHistoryPanel
              data={historyData}
              filter={historyFilter}
              sort={historySort}
              loading={historyLoading}
              error={historyError}
              onFilterChange={handleHistoryFilterChange}
              onPrevPage={handleHistoryPrev}
              onNextPage={handleHistoryNext}
              onRefresh={() => void fetchHistory({ page: historyData?.page ?? 1 })}
              onSortChange={handleHistorySortChange}
              onOpenGame={handleHistoryOpen}
            />
          </div>

          <div className="flex items-center justify-center gap-3 text-sm text-stone-400">
            <button
              onClick={() => router.push("/settings")}
              className="rounded-full border border-white/10 px-4 py-2 transition-colors hover:border-white/30 hover:text-stone-100"
            >
              Settings
            </button>
            <button
              onClick={() => router.push("/")}
              className="rounded-full border border-white/10 px-4 py-2 transition-colors hover:border-white/30 hover:text-stone-100"
            >
              Account
            </button>
          </div>

          {error && (
            <div className="text-center text-sm text-rose-400">
              {error}
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
