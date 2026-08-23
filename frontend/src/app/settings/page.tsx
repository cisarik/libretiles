"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useGameStore, type BoardTheme } from "@/hooks/useGameStore";
import { api } from "@/lib/api";
import { DEFAULT_FREE_MODEL_ID } from "@/lib/free-rivals";
import {
  PREMIUM_PANEL_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";
import type { AIModel } from "@/lib/types";

const TIMEOUT_CHOICES = [
  { value: 30, label: "30s", description: "Fast board read" },
  { value: 60, label: "1m", description: "Balanced search" },
  { value: 120, label: "2m", description: "Deeper lines" },
  { value: 180, label: "3m", description: "Tournament pace" },
  { value: 300, label: "5m", description: "Longest think" },
];

const STEP_CHOICES = [
  { value: 10, label: "10", description: "Quick tools" },
  { value: 20, label: "20", description: "More tries" },
  { value: 30, label: "30", description: "Default depth" },
  { value: 50, label: "50", description: "Deep search" },
  { value: 80, label: "80", description: "Max pressure" },
];

const BOARD_THEME_CHOICES: Array<{
  value: BoardTheme;
  label: string;
  description: string;
}> = [
  { value: "wood", label: "Wood", description: "Classic walnut grain" },
  { value: "black", label: "Black", description: "Glossy night lacquer" },
  { value: "green", label: "Green", description: "Dark tournament felt" },
];

const CLOSE_DELAY_MS = 220;

const MODAL_TRANSITION = {
  duration: 0.22,
  ease: [0.22, 1, 0.36, 1] as const,
};

const CATALOG_EMPTY_MESSAGE =
  "The rival catalog is empty. Seed the four free rivals to play AI matches.";

type NoticeTone = "success" | "warning" | "info";

type Notice = {
  tone: NoticeTone;
  text: string;
} | null;

function formatContextWindow(value?: number | null): string | null {
  if (!value) return null;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`;
  return `${value}`;
}

function noticeClasses(tone: NoticeTone): string {
  if (tone === "success") {
    return "border-emerald-400/25 bg-emerald-500/10 text-emerald-100";
  }
  if (tone === "warning") {
    return "border-amber-400/25 bg-amber-500/10 text-amber-100";
  }
  return "border-sky-400/25 bg-sky-500/10 text-sky-100";
}

function resolveEligibleModelId(
  eligibleIds: string[],
  preferredId: string | null | undefined,
  storedId: string | null | undefined,
): string | null {
  if (preferredId && eligibleIds.includes(preferredId)) return preferredId;
  if (storedId && eligibleIds.includes(storedId)) return storedId;
  if (eligibleIds.includes(DEFAULT_FREE_MODEL_ID)) return DEFAULT_FREE_MODEL_ID;
  return eligibleIds[0] ?? null;
}

function SettingsPanel({
  title,
  description,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`relative overflow-hidden rounded-[1.6rem] border border-white/8 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.22)] transition-[border-color,box-shadow,transform] duration-300 hover:border-amber-200/20 hover:shadow-[0_20px_45px_rgba(0,0,0,0.26)] ${className}`}
      style={PREMIUM_PANEL_STYLE}
      onMouseMove={handlePremiumSurfacePointer}
    >
      <div className="absolute inset-x-5 top-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
      <div className="mb-4">
        <h2 className="text-xl font-black uppercase tracking-[0.12em] text-stone-50 sm:text-[1.65rem]">
          <span className="font-gold-shiny">{title}</span>
        </h2>
        {description ? (
          <p className="mt-2 text-sm uppercase tracking-[0.14em] text-stone-500">
            {description}
          </p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function ChoiceGrid({
  title,
  description,
  choices,
  selectedValue,
  onSelect,
}: {
  title: string;
  description?: string;
  choices: Array<{ value: number; label: string; description: string }>;
  selectedValue: number;
  onSelect: (value: number) => void;
}) {
  return (
    <SettingsPanel title={title} description={description}>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(132px,1fr))] gap-3">
        {choices.map((choice) => {
          const isSelected = selectedValue === choice.value;
          return (
            <motion.button
              key={choice.value}
              type="button"
              whileHover={{ y: -1.5, scale: 1.01 }}
              whileTap={{ scale: 0.985 }}
              onClick={() => onSelect(choice.value)}
              className={`min-h-[154px] rounded-[1.15rem] border px-4 py-4 text-left transition-[border-color,box-shadow,background-color,transform] duration-300 md:min-h-[162px] ${
                isSelected
                  ? "border-amber-300/45 bg-amber-400/10 shadow-[0_12px_30px_rgba(251,191,36,0.10)]"
                  : "border-white/8 bg-stone-950/72 hover:border-white/14 hover:shadow-[0_12px_28px_rgba(0,0,0,0.2)]"
              }`}
            >
              <div
                className={`text-lg font-black uppercase tracking-[0.08em] sm:text-[1.65rem] ${
                  isSelected ? "text-amber-100" : "text-stone-100"
                }`}
              >
                {choice.label}
              </div>
              <div className="mt-2 text-[0.92rem] uppercase leading-7 tracking-[0.1em] text-stone-400 sm:text-[0.98rem]">
                {choice.description}
              </div>
            </motion.button>
          );
        })}
      </div>
    </SettingsPanel>
  );
}

function BoardSurfacePanel({
  selectedTheme,
  onSelect,
}: {
  selectedTheme: BoardTheme;
  onSelect: (theme: BoardTheme) => void;
}) {
  return (
    <SettingsPanel
      title="Board Surface"
      description="Saved on this device and used in the game board."
    >
      <div className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">
        {BOARD_THEME_CHOICES.map((choice) => {
          const isSelected = selectedTheme === choice.value;
          return (
            <motion.button
              key={choice.value}
              type="button"
              whileHover={{ y: -1.5, scale: 1.01 }}
              whileTap={{ scale: 0.985 }}
              onClick={() => onSelect(choice.value)}
              className={`rounded-[1.15rem] border p-3 text-left transition-[border-color,box-shadow,background-color,transform] duration-300 ${
                isSelected
                  ? "border-amber-300/45 bg-amber-400/10 shadow-[0_12px_30px_rgba(251,191,36,0.10)]"
                  : "border-white/8 bg-stone-950/72 hover:border-white/14 hover:shadow-[0_12px_28px_rgba(0,0,0,0.2)]"
              }`}
            >
              <div
                data-theme={choice.value}
                className="board-surface-swatch aspect-square w-full"
              />
              <div className="mt-3 flex items-center justify-between gap-3">
                <span className="font-gold-dark text-[1.2rem] font-black leading-none">
                  {choice.label}
                </span>
                {isSelected ? (
                  <span className="rounded-full border border-amber-300/24 bg-amber-300/12 px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-amber-100">
                    Active
                  </span>
                ) : null}
              </div>
              <div className="mt-2 text-[0.85rem] uppercase tracking-[0.1em] text-stone-400">
                {choice.description}
              </div>
            </motion.button>
          );
        })}
      </div>
    </SettingsPanel>
  );
}

function ShinyEffectPanel({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  return (
    <SettingsPanel
      title="Shiny Effect"
      description="Turn the live sheen off when you want a lighter GPU load."
    >
      <div className="grid grid-cols-2 gap-3">
        {[
          { value: true, label: "On", description: "Animated board sheen" },
          { value: false, label: "Off", description: "Lower GPU load" },
        ].map((choice) => {
          const isSelected = enabled === choice.value;
          return (
            <motion.button
              key={choice.label}
              type="button"
              whileHover={{ y: -1.5, scale: 1.01 }}
              whileTap={{ scale: 0.985 }}
              onClick={() => onToggle(choice.value)}
              className={`min-h-[154px] rounded-[1.15rem] border px-4 py-4 text-left transition-[border-color,box-shadow,background-color,transform] duration-300 ${
                isSelected
                  ? "border-amber-300/45 bg-amber-400/10 shadow-[0_12px_30px_rgba(251,191,36,0.10)]"
                  : "border-white/8 bg-stone-950/72 hover:border-white/14 hover:shadow-[0_12px_28px_rgba(0,0,0,0.2)]"
              }`}
            >
              <div
                className={`text-[1.45rem] font-black uppercase tracking-[0.08em] ${
                  isSelected ? "text-amber-100" : "text-stone-100"
                }`}
              >
                {choice.label}
              </div>
              <div className="mt-3 text-[0.95rem] uppercase leading-7 tracking-[0.1em] text-stone-400">
                {choice.description}
              </div>
            </motion.button>
          );
        })}
      </div>
    </SettingsPanel>
  );
}

function PremiumLookPanel({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  return (
    <SettingsPanel
      title="Premium Look"
      description="Interactive amber spotlight for the game header and rack panel."
    >
      <div className="grid grid-cols-2 gap-3">
        {[
          { value: true, label: "On", description: "Premium interactive panels" },
          { value: false, label: "Off", description: "Classic dark surfaces" },
        ].map((choice) => {
          const isSelected = enabled === choice.value;
          return (
            <motion.button
              key={choice.label}
              type="button"
              whileHover={{ y: -1.5, scale: 1.01 }}
              whileTap={{ scale: 0.985 }}
              onClick={() => onToggle(choice.value)}
              className={`min-h-[154px] rounded-[1.15rem] border px-4 py-4 text-left transition-[border-color,box-shadow,background-color,transform] duration-300 ${
                isSelected
                  ? "border-amber-300/45 bg-amber-400/10 shadow-[0_12px_30px_rgba(251,191,36,0.10)]"
                  : "border-white/8 bg-stone-950/72 hover:border-white/14 hover:shadow-[0_12px_28px_rgba(0,0,0,0.2)]"
              }`}
            >
              <div
                className={`text-[1.45rem] font-black uppercase tracking-[0.08em] ${
                  isSelected ? "text-amber-100" : "text-stone-100"
                }`}
              >
                {choice.label}
              </div>
              <div className="mt-3 text-[0.95rem] uppercase leading-7 tracking-[0.1em] text-stone-400">
                {choice.description}
              </div>
            </motion.button>
          );
        })}
      </div>
    </SettingsPanel>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const token = useGameStore((s) => s.token);
  const setCreditBalance = useGameStore((s) => s.setCreditBalance);
  const selectedModelId = useGameStore((s) => s.selectedModelId);
  const setSelectedModelId = useGameStore((s) => s.setSelectedModelId);
  const aiTimeout = useGameStore((s) => s.aiTimeout);
  const setAITimeout = useGameStore((s) => s.setAITimeout);
  const aiMaxSteps = useGameStore((s) => s.aiMaxSteps);
  const setAIMaxSteps = useGameStore((s) => s.setAIMaxSteps);
  const boardTheme = useGameStore((s) => s.boardTheme);
  const setBoardTheme = useGameStore((s) => s.setBoardTheme);
  const boardShineEnabled = useGameStore((s) => s.boardShineEnabled);
  const setBoardShineEnabled = useGameStore((s) => s.setBoardShineEnabled);
  const premiumLookEnabled = useGameStore((s) => s.premiumLookEnabled);
  const setPremiumLookEnabled = useGameStore((s) => s.setPremiumLookEnabled);

  const [models, setModels] = useState<AIModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingModelId, setSavingModelId] = useState<string | null>(null);
  const [startingNewGame, setStartingNewGame] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [accountSyncAvailable, setAccountSyncAvailable] = useState(false);
  const [isClosing, setIsClosing] = useState(false);
  const rivalSectionRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [catalogResult, profileResult] = await Promise.all([
          api.getModels().then(
            (catalog) => ({ ok: true as const, catalog }),
            () => ({ ok: false as const, catalog: [] as AIModel[] }),
          ),
          token
            ? api.me(token).then(
                (profile) => ({ ok: true as const, profile }),
                () => ({ ok: false as const, profile: null }),
              )
            : Promise.resolve({ ok: false as const, profile: null }),
        ]);

        if (cancelled) return;

        const nextModels = Array.isArray(catalogResult.catalog)
          ? catalogResult.catalog
          : [];
        const eligibleIds = nextModels.map((model) => model.model_id);
        const storedId = useGameStore.getState().selectedModelId;
        const preferredId = profileResult.profile?.preferred_ai_model_id ?? "";

        setModels(nextModels);
        setAccountSyncAvailable(profileResult.ok);

        if (profileResult.profile) {
          setCreditBalance(profileResult.profile.credit_balance);
        } else if (token) {
          setNotice({
            tone: "info",
            text: "Account sync is unavailable right now. Settings still work locally on this device.",
          });
        }

        const resolved = resolveEligibleModelId(eligibleIds, preferredId, storedId);

        if (!resolved) {
          setNotice({
            tone: "warning",
            text: CATALOG_EMPTY_MESSAGE,
          });
          return;
        }

        if (resolved !== storedId) {
          setSelectedModelId(resolved);
        }

        if (token && profileResult.ok && preferredId && preferredId !== resolved) {
          try {
            await api.updateMe(token, { preferred_ai_model_id: resolved });
          } catch {
            if (!cancelled) {
              setNotice({
                tone: "info",
                text: "A free rival is selected on this device. Account preference could not be repaired yet.",
              });
            }
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [token, setCreditBalance, setSelectedModelId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const focusRival =
      new URLSearchParams(window.location.search).get("focus") === "rival";
    if (!focusRival) return;
    const frame = window.requestAnimationFrame(() => {
      rivalSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const selectedModel = useMemo(
    () => models.find((model) => model.model_id === selectedModelId) ?? null,
    [models, selectedModelId],
  );

  async function handleClose() {
    if (isClosing) return;
    setIsClosing(true);
    await new Promise((resolve) => window.setTimeout(resolve, CLOSE_DELAY_MS));
    router.back();
  }

  useEffect(() => {
    let timeoutId: number | null = null;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || isClosing) return;
      setIsClosing(true);
      timeoutId = window.setTimeout(() => router.back(), CLOSE_DELAY_MS);
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [isClosing, router]);

  async function persistModelSelection(modelId: string) {
    if (modelId === selectedModelId || savingModelId) return;
    if (!models.some((model) => model.model_id === modelId)) return;

    const previousModelId = selectedModelId;
    const chosenModel = models.find((model) => model.model_id === modelId);

    setNotice(null);
    setSelectedModelId(modelId);

    if (!token || !accountSyncAvailable) {
      setNotice({
        tone: "info",
        text: `${chosenModel?.display_name ?? modelId} is active on this device.`,
      });
      return;
    }

    setSavingModelId(modelId);
    try {
      const profile = await api.updateMe(token, { preferred_ai_model_id: modelId });
      setCreditBalance(profile.credit_balance);
      setNotice({
        tone: "success",
        text: `${chosenModel?.display_name ?? modelId} will be used for the next AI turn.`,
      });
    } catch {
      setSelectedModelId(previousModelId);
      setNotice({
        tone: "warning",
        text: "Model change did not sync to your account. Try again in a moment.",
      });
    } finally {
      setSavingModelId(null);
    }
  }

  async function handleNewGame() {
    if (!token) {
      router.push("/");
      return;
    }

    setStartingNewGame(true);
    setNotice(null);
    try {
      router.push("/play");
    } catch {
      setNotice({
        tone: "warning",
        text: "Could not start a fresh game right now.",
      });
    } finally {
      setStartingNewGame(false);
    }
  }

  return (
    <div className="relative min-h-[100svh] overflow-hidden bg-[radial-gradient(circle_at_top,rgba(126,84,26,0.22),transparent_28%),linear-gradient(180deg,#0f0c09,#080706)] px-3 py-3 text-stone-100 sm:px-4 sm:py-4 xl:px-5 xl:py-5">
      <motion.div
        className="absolute inset-0 bg-black/48 backdrop-blur-[2px]"
        initial={{ opacity: 0 }}
        animate={{ opacity: isClosing ? 0 : 1 }}
        transition={MODAL_TRANSITION}
        onClick={() => void handleClose()}
      />

      <motion.div
        className="relative mx-auto flex max-h-[calc(100svh-1rem)] max-w-[1400px] flex-col overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(24,20,16,0.96),rgba(11,9,8,0.98))] shadow-[0_30px_100px_rgba(0,0,0,0.5)] backdrop-blur-xl sm:max-h-[calc(100svh-2rem)] sm:rounded-[2.35rem]"
        initial={{ opacity: 0, y: 28, scale: 0.965 }}
        animate={{
          opacity: isClosing ? 0 : 1,
          y: isClosing ? 20 : 0,
          scale: isClosing ? 0.985 : 1,
        }}
        transition={MODAL_TRANSITION}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="pointer-events-none absolute inset-x-12 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/70 to-transparent" />
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(251,191,36,0.08),transparent_34%)]" />

        <div className="relative border-b border-white/8 px-4 py-4 sm:px-5 sm:py-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-gold-shiny text-3xl font-black tracking-tight sm:text-[2.7rem]">
                Settings
              </h1>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <motion.button
                type="button"
                whileHover={{ y: -1.5 }}
                whileTap={{ scale: 0.985 }}
                onClick={() => void handleClose()}
                className="rounded-full border border-amber-300/26 bg-[linear-gradient(135deg,rgba(251,191,36,0.12),rgba(255,255,255,0.04))] px-5 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18),0_0_24px_rgba(251,191,36,0.08)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-amber-200/50 hover:bg-[linear-gradient(135deg,rgba(251,191,36,0.18),rgba(255,255,255,0.06))] hover:shadow-[0_14px_30px_rgba(0,0,0,0.24),0_0_30px_rgba(251,191,36,0.14)]"
              >
                <span className="font-gold-shiny text-[1.12rem] font-black leading-none">
                  Back to game
                </span>
              </motion.button>
              <motion.button
                type="button"
                whileHover={{ y: -1.5 }}
                whileTap={{ scale: 0.985 }}
                onClick={() => void handleNewGame()}
                disabled={startingNewGame}
                className="rounded-full border border-amber-200/40 bg-[linear-gradient(135deg,rgba(251,191,36,0.18),rgba(245,158,11,0.08))] px-5 py-2.5 shadow-[0_10px_24px_rgba(251,191,36,0.12),0_0_28px_rgba(251,191,36,0.12)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-amber-100/60 hover:bg-[linear-gradient(135deg,rgba(251,191,36,0.24),rgba(245,158,11,0.12))] hover:shadow-[0_12px_28px_rgba(251,191,36,0.18),0_0_34px_rgba(251,191,36,0.18)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span className="font-gold-shiny text-[1.12rem] font-black leading-none">
                  {startingNewGame ? "Starting..." : "New game"}
                </span>
              </motion.button>
            </div>

            {notice && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18 }}
                className={`mt-4 rounded-[1.2rem] border px-4 py-3 text-sm shadow-[0_14px_32px_rgba(0,0,0,0.16)] ${noticeClasses(
                  notice.tone,
                )}`}
              >
                {notice.text}
              </motion.div>
            )}
          </div>
        </div>

        <div className="ornate-scrollbar relative min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
          <div className="flex min-h-0 flex-col gap-4">
            <section ref={rivalSectionRef} className="min-h-0">
              <SettingsPanel
                title="Choose the rival"
                description="Free OpenRouter rivals from the live catalog."
              >
                <div className="mb-4 min-w-0">
                  <div
                    className={`truncate text-[1.35rem] font-black sm:text-[1.55rem] ${
                      selectedModel ? "font-gold-shiny" : "text-stone-400"
                    }`}
                  >
                    {selectedModel?.display_name ?? "No rival selected"}
                  </div>
                  {savingModelId ? (
                    <div className="mt-3 inline-flex rounded-full border border-amber-300/20 bg-amber-400/10 px-3 py-1.5 text-xs font-medium text-amber-100 shadow-[0_10px_24px_rgba(251,191,36,0.08)]">
                      Saving selection...
                    </div>
                  ) : null}
                </div>

                {loading ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {Array.from({ length: 4 }).map((_, index) => (
                      <div
                        key={index}
                        className="min-h-[168px] animate-pulse rounded-[1.15rem] border border-white/8 bg-black/12"
                      />
                    ))}
                  </div>
                ) : models.length > 0 ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {models.map((model) => {
                      const isSelected = selectedModelId === model.model_id;
                      const isSaving = savingModelId === model.model_id;
                      const contextLabel = formatContextWindow(model.context_window);

                      return (
                        <motion.button
                          key={model.model_id}
                          type="button"
                          whileHover={{ y: -1.5, scale: 1.01 }}
                          whileTap={{ scale: 0.985 }}
                          disabled={Boolean(savingModelId)}
                          aria-pressed={isSelected}
                          onClick={() => void persistModelSelection(model.model_id)}
                          className={`rounded-[1.15rem] border px-4 py-4 text-left transition-[border-color,box-shadow,background-color,transform] duration-300 disabled:cursor-not-allowed disabled:opacity-75 ${
                            isSelected
                              ? "border-amber-300/45 bg-amber-400/10 shadow-[0_12px_30px_rgba(251,191,36,0.10)]"
                              : "border-white/8 bg-stone-950/72 hover:border-white/14 hover:shadow-[0_12px_28px_rgba(0,0,0,0.2)]"
                          }`}
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`text-[1.2rem] font-black sm:text-[1.32rem] ${
                                isSelected ? "font-gold-shiny" : "font-gold-dark"
                              }`}
                            >
                              {model.display_name}
                            </span>
                            <span className="rounded-full border border-emerald-300/26 bg-emerald-300/14 px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-emerald-50">
                              Free
                            </span>
                            {model.is_flagship ? (
                              <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-300">
                                Recommended
                              </span>
                            ) : null}
                            {isSaving || isSelected ? (
                              <span
                                className={`rounded-full border px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] ${
                                  isSaving
                                    ? "border-sky-400/24 bg-sky-400/12 text-sky-100"
                                    : "border-amber-300/24 bg-amber-300/12 text-amber-100"
                                }`}
                              >
                                {isSaving ? "Saving" : "Active"}
                              </span>
                            ) : null}
                          </div>
                          {model.description ? (
                            <p className="mt-3 text-[0.98rem] leading-7 text-stone-300">
                              {model.description}
                            </p>
                          ) : null}
                          {contextLabel ? (
                            <div className="mt-3 text-[0.78rem] uppercase tracking-[0.16em] text-stone-500">
                              {contextLabel} context
                            </div>
                          ) : null}
                        </motion.button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="rounded-[1.15rem] border border-white/8 bg-stone-950/72 px-4 py-5 text-sm text-stone-400">
                    {CATALOG_EMPTY_MESSAGE}
                  </div>
                )}
              </SettingsPanel>
            </section>

            <div className="grid w-full gap-4 xl:grid-cols-2">
              <ChoiceGrid
                title="AI Thinking Time"
                choices={TIMEOUT_CHOICES}
                selectedValue={aiTimeout}
                onSelect={setAITimeout}
              />

              <ChoiceGrid
                title="Search Steps"
                choices={STEP_CHOICES}
                selectedValue={aiMaxSteps}
                onSelect={setAIMaxSteps}
              />

              <BoardSurfacePanel
                selectedTheme={boardTheme}
                onSelect={setBoardTheme}
              />

              <ShinyEffectPanel
                enabled={boardShineEnabled}
                onToggle={setBoardShineEnabled}
              />

              <PremiumLookPanel
                enabled={premiumLookEnabled}
                onToggle={setPremiumLookEnabled}
              />
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
