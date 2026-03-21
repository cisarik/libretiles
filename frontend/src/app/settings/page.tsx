"use client";

import {
  useEffect,
  useState,
  type CSSProperties,
  type MouseEvent,
} from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";
import { api } from "@/lib/api";
import type { AIModel, CreateGameResponse } from "@/lib/types";

const PROVIDER_ICONS: Record<string, string> = {
  openai: "🤖",
  google: "🔮",
  anthropic: "🧠",
  openrouter: "🌐",
  novita: "⚡",
  xai: "⚙️",
};

const QUALITY_COLORS: Record<string, string> = {
  basic: "bg-stone-700/80 text-stone-200",
  standard: "bg-sky-500/20 text-sky-200",
  premium: "bg-amber-400/20 text-amber-200",
  elite: "bg-rose-500/20 text-rose-100",
};

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

const CLOSE_DELAY_MS = 220;

const MODAL_TRANSITION = {
  duration: 0.22,
  ease: [0.22, 1, 0.36, 1] as const,
};

const INTERACTIVE_PANEL_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(240px circle at var(--spotlight-x, 50%) var(--spotlight-y, 50%), rgba(251,191,36,0.12), transparent 64%), linear-gradient(180deg, rgba(25,21,18,0.92), rgba(14,12,10,0.97))",
};

const CREDIT_PANEL_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(320px circle at var(--spotlight-x, 48%) var(--spotlight-y, 45%), rgba(255,215,128,0.24), transparent 60%), linear-gradient(145deg, rgba(39,26,12,0.98), rgba(14,11,8,0.98))",
};

type NoticeTone = "success" | "warning" | "info";

type Notice = {
  tone: NoticeTone;
  text: string;
} | null;

function formatContextWindow(value?: number | null): string {
  if (!value) return "n/a";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`;
  return `${value}`;
}

function formatUsdPerToken(value?: string): string {
  const numeric = Number.parseFloat(value ?? "");
  if (!Number.isFinite(numeric)) return "n/a";

  const perToken = numeric / 1_000_000;
  const digits = perToken >= 0.0001 ? 6 : 8;
  return `$${perToken.toFixed(digits).replace(/0+$/, "").replace(/\.$/, "")}`;
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

function handleSurfacePointer(event: MouseEvent<HTMLElement>) {
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  event.currentTarget.style.setProperty("--spotlight-x", `${x}px`);
  event.currentTarget.style.setProperty("--spotlight-y", `${y}px`);
}

function PriceStat({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-[1.1rem] border px-3 py-2.5 transition-[border-color,box-shadow,background-color] duration-300 ${
        accent
          ? "border-amber-300/25 bg-amber-400/8 shadow-[0_8px_24px_rgba(251,191,36,0.08)]"
          : "border-white/8 bg-stone-950/70 hover:border-white/12 hover:shadow-[0_12px_28px_rgba(0,0,0,0.22)]"
      }`}
    >
      <div className="text-[0.62rem] uppercase tracking-[0.28em] text-stone-500">
        {label}
      </div>
      <div
        className={`mt-1 text-base font-semibold ${
          accent ? "text-amber-100" : "text-stone-100"
        }`}
      >
        {value}
      </div>
    </div>
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
  description: string;
  choices: Array<{ value: number; label: string; description: string }>;
  selectedValue: number;
  onSelect: (value: number) => void;
}) {
  return (
    <section
      className="relative overflow-hidden rounded-[1.6rem] border border-white/8 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.22)] transition-[border-color,box-shadow,transform] duration-300 hover:border-amber-200/20 hover:shadow-[0_20px_45px_rgba(0,0,0,0.26)]"
      style={INTERACTIVE_PANEL_STYLE}
      onMouseMove={handleSurfacePointer}
    >
      <div className="absolute inset-x-5 top-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
      <div className="mb-3">
        <h2 className="text-base font-semibold text-stone-50">{title}</h2>
        <p className="mt-1 text-xs leading-5 text-stone-400">{description}</p>
      </div>

      <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-3">
        {choices.map((choice) => {
          const isSelected = selectedValue === choice.value;
          return (
            <motion.button
              key={choice.value}
              type="button"
              whileHover={{ y: -1.5, scale: 1.01 }}
              whileTap={{ scale: 0.985 }}
              onClick={() => onSelect(choice.value)}
              className={`rounded-[1.1rem] border px-2.5 py-3 text-left transition-[border-color,box-shadow,background-color,transform] duration-300 ${
                isSelected
                  ? "border-amber-300/45 bg-amber-400/10 shadow-[0_12px_30px_rgba(251,191,36,0.10)]"
                  : "border-white/8 bg-stone-950/72 hover:border-white/14 hover:shadow-[0_12px_28px_rgba(0,0,0,0.2)]"
              }`}
            >
              <div
                className={`text-base font-black ${
                  isSelected ? "text-amber-100" : "text-stone-100"
                }`}
              >
                {choice.label}
              </div>
              <div className="mt-1 text-[0.66rem] leading-4 text-stone-500">
                {choice.description}
              </div>
            </motion.button>
          );
        })}
      </div>
    </section>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const token = useGameStore((s) => s.token);
  const creditBalance = useGameStore((s) => s.creditBalance);
  const setCreditBalance = useGameStore((s) => s.setCreditBalance);
  const selectedModelId = useGameStore((s) => s.selectedModelId);
  const setSelectedModelId = useGameStore((s) => s.setSelectedModelId);
  const aiTimeout = useGameStore((s) => s.aiTimeout);
  const setAITimeout = useGameStore((s) => s.setAITimeout);
  const aiMaxSteps = useGameStore((s) => s.aiMaxSteps);
  const setAIMaxSteps = useGameStore((s) => s.setAIMaxSteps);

  const [models, setModels] = useState<AIModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingModelId, setSavingModelId] = useState<string | null>(null);
  const [startingNewGame, setStartingNewGame] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [accountSyncAvailable, setAccountSyncAvailable] = useState(false);
  const [isClosing, setIsClosing] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [catalog, profileResult] = await Promise.all([
          fetch("/api/models").then((r) => r.json()).catch(() => []),
          token
            ? api
                .me(token)
                .then((profile) => ({ ok: true, profile }))
                .catch(() => ({ ok: false, profile: null }))
            : Promise.resolve({ ok: false, profile: null }),
        ]);

        if (cancelled) return;

        const nextModels = Array.isArray(catalog) ? (catalog as AIModel[]) : [];
        const localSelectedModelId = useGameStore.getState().selectedModelId;
        setModels(nextModels);
        setAccountSyncAvailable(profileResult.ok);

        if (profileResult.profile) {
          setCreditBalance(profileResult.profile.credit_balance);
          if (
            profileResult.profile.preferred_ai_model_id &&
            nextModels.some(
              (model) => model.model_id === profileResult.profile.preferred_ai_model_id,
            )
          ) {
            setSelectedModelId(profileResult.profile.preferred_ai_model_id);
          }
        } else if (token) {
          setNotice({
            tone: "info",
            text: "Account sync is unavailable right now. Settings still work locally on this device.",
          });
        }

        if (
          nextModels.length > 0 &&
          !nextModels.some((model) => model.model_id === localSelectedModelId)
        ) {
          setSelectedModelId(nextModels[0].model_id);
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

  const selectedModel =
    models.find((model) => model.model_id === selectedModelId) ?? models[0] ?? null;

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

    const nextModelId = selectedModel?.model_id ?? selectedModelId;
    if (!nextModelId) return;

    setStartingNewGame(true);
    setNotice(null);
    try {
      const result = (await api.createGame(token, {
        game_mode: "vs_ai",
        ai_model_model_id: nextModelId,
      })) as CreateGameResponse;
      router.push(`/draw/${result.game_id}`);
    } catch {
      setNotice({
        tone: "warning",
        text: "Could not start a fresh game right now.",
      });
    } finally {
      setStartingNewGame(false);
    }
  }

  function handleTopUpCredit() {
    setNotice({
      tone: "info",
      text: "Top-up checkout lands next. The live credit countdown is already wired into the game now.",
    });
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-[radial-gradient(circle_at_top,rgba(126,84,26,0.20),transparent_28%),linear-gradient(180deg,#0f0c09,#080706)] px-3 py-3 text-stone-100 sm:px-5 sm:py-5">
      <motion.div
        className="absolute inset-0 bg-black/48 backdrop-blur-[2px]"
        initial={{ opacity: 0 }}
        animate={{ opacity: isClosing ? 0 : 1 }}
        transition={MODAL_TRANSITION}
        onClick={() => void handleClose()}
      />

      <motion.div
        className="relative mx-auto flex max-h-[calc(100vh-1.5rem)] max-w-[1120px] flex-col overflow-hidden rounded-[2.2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(24,20,16,0.96),rgba(11,9,8,0.98))] shadow-[0_30px_100px_rgba(0,0,0,0.5)] backdrop-blur-xl sm:max-h-[calc(100vh-2.5rem)]"
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

        <div className="relative border-b border-white/8 px-4 py-4 sm:px-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="text-[0.68rem] uppercase tracking-[0.34em] text-amber-200/70">
                Control Room
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-black tracking-tight text-stone-50 sm:text-[2rem]">
                  Settings
                </h1>
                <span className="rounded-full border border-white/8 bg-white/5 px-3 py-1 text-[0.68rem] uppercase tracking-[0.26em] text-stone-400">
                  Tablet mode
                </span>
              </div>
              <p className="mt-2 max-w-2xl text-sm text-stone-400">
                Compact AI setup with live pricing, subtle motion, and faster in-game decisions.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <motion.button
                type="button"
                whileHover={{ y: -1.5 }}
                whileTap={{ scale: 0.985 }}
                onClick={() => void handleNewGame()}
                disabled={startingNewGame}
                className="rounded-full border border-amber-300/30 bg-amber-300/12 px-4 py-2 text-sm font-semibold text-amber-100 shadow-[0_10px_24px_rgba(251,191,36,0.10)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-amber-200/50 hover:bg-amber-300/18 hover:shadow-[0_12px_28px_rgba(251,191,36,0.16)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {startingNewGame ? "Starting..." : "New game"}
              </motion.button>
              <motion.button
                type="button"
                whileHover={{ y: -1.5 }}
                whileTap={{ scale: 0.985 }}
                onClick={() => void handleClose()}
                className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-stone-200 shadow-[0_10px_24px_rgba(0,0,0,0.18)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-white/16 hover:bg-white/8 hover:shadow-[0_14px_30px_rgba(0,0,0,0.24)]"
              >
                Back to game
              </motion.button>
            </div>
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

        <div className="relative grid flex-1 min-h-0 gap-4 overflow-hidden p-4 sm:p-5 lg:grid-cols-[minmax(0,1.26fr)_minmax(320px,0.82fr)]">
          <section className="min-h-0 overflow-y-auto pr-1">
            <div className="flex flex-col gap-2 pb-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="text-[0.68rem] uppercase tracking-[0.3em] text-stone-500">
                  AI Opponent
                </div>
                <h2 className="mt-2 text-xl font-black text-stone-50 sm:text-2xl">
                  Choose the rival
                </h2>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-stone-400">
                  Top synced models only. Prices come from the backend catalog, and credit is deducted from the same numbers.
                </p>
              </div>
              {savingModelId && (
                <div className="rounded-full border border-amber-300/20 bg-amber-400/10 px-3 py-1.5 text-xs font-medium text-amber-100 shadow-[0_10px_24px_rgba(251,191,36,0.08)]">
                  Updating {savingModelId}...
                </div>
              )}
            </div>

            {loading ? (
              <div className="grid gap-3 md:grid-cols-2">
                {Array.from({ length: 6 }).map((_, index) => (
                  <div
                    key={index}
                    className="h-48 animate-pulse rounded-[1.6rem] border border-white/8 bg-stone-900/60"
                  />
                ))}
              </div>
            ) : models.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2">
                {models.map((model, index) => {
                  const isSelected = selectedModelId === model.model_id;
                  const isSaving = savingModelId === model.model_id;

                  return (
                    <motion.button
                      key={model.model_id}
                      type="button"
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.025 }}
                      whileHover={{ y: -3, scale: 1.008 }}
                      whileTap={{ scale: 0.988 }}
                      onMouseMove={handleSurfacePointer}
                      onClick={() => void persistModelSelection(model.model_id)}
                      disabled={Boolean(savingModelId)}
                      className={`relative overflow-hidden rounded-[1.7rem] border p-4 text-left transition-[border-color,box-shadow,transform,background-color] duration-300 ${
                        isSelected
                          ? "border-amber-300/40 shadow-[0_18px_45px_rgba(251,191,36,0.10)]"
                          : "border-white/8 shadow-[0_18px_42px_rgba(0,0,0,0.20)] hover:border-white/14 hover:shadow-[0_20px_48px_rgba(0,0,0,0.24)]"
                      } disabled:cursor-not-allowed disabled:opacity-75`}
                      style={INTERACTIVE_PANEL_STYLE}
                    >
                      <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/12 to-transparent" />
                      <div
                        className={`pointer-events-none absolute inset-0 rounded-[inherit] transition-opacity duration-300 ${
                          isSelected ? "opacity-100" : "opacity-0"
                        }`}
                        style={{
                          background:
                            "linear-gradient(180deg, rgba(251,191,36,0.08), transparent 42%)",
                        }}
                      />

                      <div className="relative flex h-full flex-col gap-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex min-w-0 items-start gap-3">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[1rem] border border-white/10 bg-stone-950/78 text-2xl shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
                              {PROVIDER_ICONS[model.provider] || "🔧"}
                            </div>
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <div className="truncate text-[1.12rem] font-black text-stone-50">
                                  {model.display_name}
                                </div>
                                {model.is_flagship && (
                                  <span className="rounded-full border border-amber-300/20 bg-amber-400/12 px-2 py-0.5 text-[0.58rem] font-semibold uppercase tracking-[0.22em] text-amber-100">
                                    flagship
                                  </span>
                                )}
                              </div>
                              <div className="mt-1 break-all font-mono text-[0.7rem] text-stone-500">
                                {model.model_id}
                              </div>
                            </div>
                          </div>

                          <div
                            className={`rounded-full px-2.5 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.22em] ${
                              QUALITY_COLORS[model.quality_tier] || QUALITY_COLORS.standard
                            }`}
                          >
                            {isSaving ? "Saving" : isSelected ? "Selected" : model.quality_tier}
                          </div>
                        </div>

                        {model.description && (
                          <p className="min-h-[3.5rem] text-sm leading-6 text-stone-400">
                            {model.description}
                          </p>
                        )}

                        <div className="grid grid-cols-2 gap-2.5">
                          <PriceStat label="Input / 1M" value={`$${model.input_cost_per_million}`} />
                          <PriceStat label="Output / 1M" value={`$${model.output_cost_per_million}`} />
                          <PriceStat label="Cache / 1M" value={`$${model.cache_read_cost_per_million}`} />
                          <PriceStat
                            label="$ / token"
                            value={formatUsdPerToken(model.combined_cost_per_million)}
                            accent={isSelected}
                          />
                        </div>

                        <div className="mt-auto flex items-center justify-between gap-3 pt-1 text-xs text-stone-500">
                          <span>Context {formatContextWindow(model.context_window)}</span>
                          <span className={isSelected ? "text-amber-100" : "text-stone-500"}>
                            {isSelected ? "Active now" : "Click to activate"}
                          </span>
                        </div>
                      </div>
                    </motion.button>
                  );
                })}
              </div>
            ) : (
              <div
                className="rounded-[1.7rem] border border-white/8 p-5 text-sm text-stone-400 shadow-[0_16px_40px_rgba(0,0,0,0.20)]"
                style={INTERACTIVE_PANEL_STYLE}
                onMouseMove={handleSurfacePointer}
              >
                No synced models are available yet. Run{" "}
                <span className="font-mono text-stone-200">
                  python manage.py sync_gateway_models
                </span>{" "}
                first.
              </div>
            )}
          </section>

          <aside className="min-h-0 overflow-y-auto pl-0 lg:pl-1">
            <div className="space-y-4">
              <motion.section
                whileHover={{ y: -2, scale: 1.004 }}
                className="relative overflow-hidden rounded-[1.8rem] border border-amber-300/20 p-5 shadow-[0_20px_55px_rgba(0,0,0,0.30)] transition-[border-color,box-shadow,transform] duration-300 hover:border-amber-200/28 hover:shadow-[0_24px_60px_rgba(0,0,0,0.34)]"
                style={CREDIT_PANEL_STYLE}
                onMouseMove={handleSurfacePointer}
              >
                <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/70 to-transparent" />
                <div className="relative">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[0.68rem] uppercase tracking-[0.3em] text-amber-100/65">
                        Credit Balance
                      </div>
                      <div className="mt-2 text-xs leading-5 text-stone-300/76">
                        Token spend is converted from the backend pricing table for the selected model.
                      </div>
                    </div>
                    <span className="rounded-full border border-white/10 bg-white/6 px-2.5 py-1 text-[0.58rem] uppercase tracking-[0.22em] text-stone-300">
                      {accountSyncAvailable ? "Synced" : token ? "Local fallback" : "Device only"}
                    </span>
                  </div>

                  <div className="mt-5 flex items-end justify-between gap-4">
                    <div>
                      <motion.div
                        whileHover={{ scale: 1.015 }}
                        className="text-4xl font-black leading-none sm:text-5xl"
                        style={{
                          fontFamily:
                            '"Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif',
                          background:
                            "linear-gradient(180deg, #fff8dc 0%, #fcd34d 38%, #f59e0b 72%, #a16207 100%)",
                          WebkitBackgroundClip: "text",
                          color: "transparent",
                          filter:
                            "drop-shadow(0 0 16px rgba(251,191,36,0.20)) drop-shadow(0 8px 18px rgba(0,0,0,0.30))",
                        }}
                      >
                        {creditBalance ?? "0.00"} cr
                      </motion.div>
                      <div className="mt-2 text-[0.62rem] uppercase tracking-[0.28em] text-amber-100/52">
                        Live balance in game
                      </div>
                    </div>

                    <motion.button
                      type="button"
                      whileHover={{ y: -1.5 }}
                      whileTap={{ scale: 0.985 }}
                      onClick={handleTopUpCredit}
                      className="rounded-full border border-amber-300/28 bg-amber-300/12 px-3.5 py-2 text-sm font-semibold text-amber-100 shadow-[0_10px_24px_rgba(251,191,36,0.12)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-amber-200/48 hover:bg-amber-300/18 hover:shadow-[0_12px_30px_rgba(251,191,36,0.16)]"
                    >
                      Top up credit
                    </motion.button>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-2.5">
                    <PriceStat
                      label="Current AI"
                      value={selectedModel?.display_name ?? "No model"}
                      accent
                    />
                    <PriceStat
                      label="$ / token"
                      value={
                        selectedModel
                          ? formatUsdPerToken(selectedModel.combined_cost_per_million)
                          : "n/a"
                      }
                    />
                  </div>
                </div>
              </motion.section>

              <section
                className="relative overflow-hidden rounded-[1.6rem] border border-white/8 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.22)] transition-[border-color,box-shadow,transform] duration-300 hover:border-amber-200/20 hover:shadow-[0_20px_45px_rgba(0,0,0,0.26)]"
                style={INTERACTIVE_PANEL_STYLE}
                onMouseMove={handleSurfacePointer}
              >
                <div className="absolute inset-x-5 top-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
                <div className="text-[0.68rem] uppercase tracking-[0.3em] text-stone-500">
                  Current setup
                </div>
                <div className="mt-4 flex items-start gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-[1rem] border border-white/10 bg-stone-950/78 text-2xl shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
                    {selectedModel ? PROVIDER_ICONS[selectedModel.provider] || "🔧" : "🎯"}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-lg font-black text-stone-50">
                        {selectedModel?.display_name ?? "Choose a model"}
                      </h2>
                      {selectedModel?.quality_tier && (
                        <span
                          className={`rounded-full px-2 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.2em] ${
                            QUALITY_COLORS[selectedModel.quality_tier] || QUALITY_COLORS.standard
                          }`}
                        >
                          {selectedModel.quality_tier}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 break-all font-mono text-[0.68rem] text-stone-500">
                      {selectedModel?.model_id ?? "No model selected"}
                    </div>
                    <p className="mt-2 text-xs leading-5 text-stone-400">
                      Click a card on the left and the next AI turn uses that model.
                    </p>
                  </div>
                </div>

                <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
                  <PriceStat
                    label="Input / 1M"
                    value={selectedModel ? `$${selectedModel.input_cost_per_million}` : "n/a"}
                  />
                  <PriceStat
                    label="Output / 1M"
                    value={selectedModel ? `$${selectedModel.output_cost_per_million}` : "n/a"}
                  />
                  <PriceStat
                    label="Cache / 1M"
                    value={selectedModel ? `$${selectedModel.cache_read_cost_per_million}` : "n/a"}
                  />
                  <PriceStat
                    label="Context"
                    value={selectedModel ? formatContextWindow(selectedModel.context_window) : "n/a"}
                  />
                </div>
              </section>

              <ChoiceGrid
                title="AI Thinking Time"
                description="Longer timeouts usually improve move quality, but they also raise token spend."
                choices={TIMEOUT_CHOICES}
                selectedValue={aiTimeout}
                onSelect={setAITimeout}
              />

              <ChoiceGrid
                title="Search Steps"
                description="How many reasoning and tool rounds the route can use before it auto-stops."
                choices={STEP_CHOICES}
                selectedValue={aiMaxSteps}
                onSelect={setAIMaxSteps}
              />
            </div>
          </aside>
        </div>
      </motion.div>
    </div>
  );
}
