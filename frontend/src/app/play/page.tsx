"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";

import { GameHistoryPanel } from "@/components/game/GameHistoryPanel";
import { variantDisplayName } from "@/components/settings/GameLanguagePanel";
import { useGameStore } from "@/hooks/useGameStore";
import { providerBadgeLabel } from "@/lib/ai-fallback";
import { api } from "@/lib/api";
import { t as translate, useLocale, useT } from "@/lib/i18n";
import { resolveEligibleModelId } from "@/lib/model-catalog";
import {
  PREMIUM_GOLD_TEXT_SHADOW_CLASS,
  PREMIUM_HEADER_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";
import type {
  AIModel,
  CreateGameResponse,
  GameHistoryFilter,
  GameHistoryItem,
  GameHistoryResponse,
  GameHistorySort,
  QueueJoinResponse,
  VariantSummary,
} from "@/lib/types";
import { reconcileSelectedVariantSlug } from "@/lib/variants";

export default function PlayPage() {
  const router = useRouter();
  const locale = useLocale();
  const { t, tf } = useT();
  const token = useGameStore((state) => state.token);
  const selectedModelId = useGameStore((state) => state.selectedModelId);
  const setSelectedModelId = useGameStore((state) => state.setSelectedModelId);
  const selectedVariantSlug = useGameStore((state) => state.selectedVariantSlug);
  const setSelectedVariantSlug = useGameStore((state) => state.setSelectedVariantSlug);
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
  const [catalogModels, setCatalogModels] = useState<AIModel[]>([]);
  const [catalogReady, setCatalogReady] = useState(false);
  const catalogMatch = catalogModels.find((model) => model.model_id === selectedModelId);
  const activeModelLabel = catalogMatch?.display_name
    ?? (catalogReady ? (catalogModels[0]?.display_name ?? t("play.rival.unavailable")) : t("play.ai.preparing"));
  const premiumTitleClass = premiumLookEnabled ? PREMIUM_GOLD_TEXT_SHADOW_CLASS : "";
  const canStartAI = catalogReady && catalogModels.length > 0;
  const queueSlug = selectedVariantSlug || "english";
  const queueVariant: VariantSummary = {
    slug: queueSlug,
    display_name: queueSlug,
    language_code: null,
    readiness: "playable",
  };
  const queueLabel = tf("play.humanQueue.queueFor", {
    variant: variantDisplayName(queueVariant, t),
  });

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
      setHistoryError(err instanceof Error ? err.message : translate(locale, "play.error.loadGames"));
    } finally {
      setHistoryLoading(false);
    }
  }, [historyFilter, historySort, locale, token]);

  const reconcileRival = useCallback(async (): Promise<{
    modelId: string | null;
    catalogReachable: boolean;
  }> => {
    if (!token) return { modelId: null, catalogReachable: true };

    const [catalogResult, profile] = await Promise.all([
      api.getModels().then(
        (catalog) => ({ ok: true as const, catalog }),
        () => ({ ok: false as const, catalog: [] as AIModel[] }),
      ),
      api.me(token).catch(() => null),
    ]);
    const catalog = catalogResult.catalog;
    setCatalogModels(catalog);

    const eligibleIds = catalog.map((model) => model.model_id);
    const storedId = useGameStore.getState().selectedModelId;
    const preferredId = profile?.preferred_ai_model_id ?? "";
    const resolved = resolveEligibleModelId(eligibleIds, preferredId, storedId);

    if (!resolved) return { modelId: null, catalogReachable: catalogResult.ok };

    if (resolved !== storedId) {
      setSelectedModelId(resolved);
    }

    if (preferredId && preferredId !== resolved) {
      try {
        await api.updateMe(token, { preferred_ai_model_id: resolved });
      } catch {
        // Preference repair is best-effort; createGame still uses the resolved catalog id.
      }
    }

    return { modelId: resolved, catalogReachable: catalogResult.ok };
  }, [token, setSelectedModelId]);

  useEffect(() => {
    if (!token) {
      router.replace("/");
      return;
    }
    void fetchHistory({ page: 1 });
  }, [fetchHistory, router, token]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    void (async () => {
      const { modelId, catalogReachable } = await reconcileRival();
      if (cancelled) return;
      setCatalogReady(true);
      if (!modelId) {
        setError(
          translate(
            locale,
            catalogReachable
              ? "play.error.catalogEmpty"
              : "play.error.catalogUnavailable",
          ),
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [locale, reconcileRival, token]);

  async function handleStartAI() {
    if (!token || startingAI) return;

    setStartingAI(true);
    setError(null);
    try {
      const { modelId, catalogReachable } = await reconcileRival();
      setCatalogReady(true);
      if (!modelId) {
        setError(
          t(
            catalogReachable
              ? "play.error.catalogEmpty"
              : "play.error.catalogUnavailable",
          ),
        );
        return;
      }

      let variantSlug = selectedVariantSlug || "english";
      try {
        const variants = await api.getVariants(token);
        const reconciled = reconcileSelectedVariantSlug(variantSlug, variants);
        if (!reconciled) {
          setError(t("play.error.variantUnavailable"));
          return;
        }
        if (reconciled !== variantSlug) {
          setSelectedVariantSlug(reconciled);
        }
        variantSlug = reconciled;
      } catch {
        setError(t("play.error.variantUnavailable"));
        return;
      }

      const result = (await api.createGame(token, {
        game_mode: "vs_ai",
        ai_model_model_id: modelId,
        variant_slug: variantSlug,
      })) as CreateGameResponse;
      resetGameUi();
      setStartingDraw(result.starting_draw);
      setStartingRack(result.human_rack);
      router.push(`/draw/${result.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("play.error.startAi"));
    } finally {
      setStartingAI(false);
    }
  }

  async function handleJoinHuman() {
    if (!token || joiningHuman) return;

    setJoiningHuman(true);
    setError(null);
    try {
      let variantSlug = selectedVariantSlug || "english";
      try {
        const variants = await api.getVariants(token);
        const reconciled = reconcileSelectedVariantSlug(variantSlug, variants);
        if (!reconciled) {
          setError(t("play.error.variantUnavailable"));
          return;
        }
        if (reconciled !== variantSlug) {
          setSelectedVariantSlug(reconciled);
        }
        variantSlug = reconciled;
      } catch {
        setError(t("play.error.variantUnavailable"));
        return;
      }

      const result = (await api.joinHumanQueue(token, {
        variant_slug: variantSlug,
      })) as QueueJoinResponse;
      resetGameUi();
      setGameState(result.state);
      if (result.waiting) {
        router.push(`/waiting/${result.state.game_id}`);
        return;
      }
      router.push(`/game/${result.state.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("play.error.joinQueue"));
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
                {t("landing.brand")}
              </div>
              <h1 className="mt-3 text-4xl font-black tracking-tight text-stone-50 sm:text-5xl">
                {t("play.title")}
              </h1>
              <p className="mt-3 text-sm text-stone-400 sm:text-base">
                {t("play.lead")}
              </p>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <button
              onClick={() => void handleStartAI()}
              disabled={startingAI || joiningHuman || !canStartAI}
              className={`group relative overflow-hidden rounded-[2rem] border border-amber-300/20 p-7 text-left shadow-[0_26px_60px_rgba(0,0,0,0.32)] transition-all hover:border-white/40 hover:shadow-[0_30px_70px_rgba(255,255,255,0.06)] disabled:opacity-50 ${premiumLookEnabled ? "backdrop-blur-[14px]" : "bg-[linear-gradient(180deg,rgba(52,34,14,0.96),rgba(18,12,9,0.98))]"}`}
              style={premiumLookEnabled ? PREMIUM_HEADER_STYLE : undefined}
              onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
            >
              <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/54 to-transparent" />
              <div className="text-[0.72rem] uppercase tracking-[0.34em] text-amber-300/70">
                {t("play.ai.eyebrow")}
              </div>
              <div className={`mt-4 font-gold-shiny text-3xl font-black leading-none text-stone-50 sm:text-[2.15rem] ${premiumTitleClass}`}>
                {t("play.ai.title")}
              </div>
              <p className="mt-3 max-w-[28rem] text-sm text-stone-300">
                {t("play.ai.body")}
              </p>
              <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-semibold text-stone-200">
                <span>{startingAI ? t("play.ai.preparing") : activeModelLabel}</span>
                {catalogMatch && !startingAI ? (
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[0.68rem] font-semibold uppercase tracking-[0.16em] ${
                      catalogMatch.provider === "nvidia-nim"
                        ? "border-violet-300/26 bg-violet-300/14 text-violet-50"
                        : "border-sky-300/26 bg-sky-300/14 text-sky-50"
                    }`}
                  >
                    {providerBadgeLabel(catalogMatch.provider)}
                  </span>
                ) : null}
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
                {t("play.humanQueue.eyebrow")}
              </div>
              <div className={`mt-4 font-gold-shiny text-3xl font-black leading-none text-stone-50 sm:text-[2.15rem] ${premiumTitleClass}`}>
                {t("play.humanQueue.title")}
              </div>
              <p className="mt-3 max-w-[28rem] text-sm text-stone-300">
                {t("play.humanQueue.body")}
              </p>
              <div className="mt-6 inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-semibold text-stone-200">
                {joiningHuman ? t("play.humanQueue.joining") : queueLabel}
              </div>
            </button>
          </div>

          <div>
            <div className="mb-3 flex items-end justify-between gap-3">
              <div>
                <div className="text-[0.72rem] uppercase tracking-[0.28em] text-stone-500">
                  {t("play.saved.eyebrow")}
                </div>
                <div className={`mt-1 font-gold-shiny text-[1.65rem] font-black leading-none sm:text-[1.9rem] ${premiumTitleClass}`}>
                  {t("play.saved.title")}
                </div>
              </div>
              <div className="hidden text-right text-sm text-stone-400 md:block">
                {t("play.saved.note")}
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
              {t("nav.settings")}
            </button>
            <button
              onClick={() => router.push("/")}
              className="rounded-full border border-white/10 px-4 py-2 transition-colors hover:border-white/30 hover:text-stone-100"
            >
              {t("nav.account")}
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
