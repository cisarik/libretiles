"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { useGameStore, type BoardTheme } from "@/hooks/useGameStore";
import { api } from "@/lib/api";
import {
  LOCAL_AI_AUTO_MODEL_ID,
  isLocalAIModelId,
} from "@/lib/local-ai";
import {
  PREMIUM_CREDIT_PANEL_STYLE,
  PREMIUM_PANEL_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";
import type { AIModel } from "@/lib/types";

const PROVIDER_ICONS: Record<string, string> = {
  lmstudio: "LM",
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

const LOCAL_CONTEXT_MIN = 512;
const LOCAL_CONTEXT_MAX = 32768;
const LOCAL_CONTEXT_PRESETS = [1256, 2048, 4096, 8192];

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

const SELECTED_ROW_CELL_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(300px circle at var(--spotlight-x, 18%) var(--spotlight-y, 50%), rgba(251,191,36,0.18), transparent 56%), linear-gradient(180deg, rgba(251,191,36,0.06), rgba(251,191,36,0.03))",
};

const SELECTED_LOCAL_ROW_CELL_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(300px circle at var(--spotlight-x, 18%) var(--spotlight-y, 50%), rgba(16,185,129,0.28), transparent 58%), linear-gradient(180deg, rgba(16,185,129,0.16), rgba(16,185,129,0.07))",
};

type NoticeTone = "success" | "warning" | "info";

type Notice = {
  tone: NoticeTone;
  text: string;
} | null;

type LocalAIStatus = {
  ok: boolean;
  reachable: boolean;
  base_url: string;
  api_base_url?: string;
  model_id: string;
  runtime_model_id?: string | null;
  loaded_context_length?: number | null;
  matching_model_loaded: boolean;
  models: string[];
  available_models: LocalAIAvailableModel[];
  error?: string;
} | null;

type LocalAIAvailableModel = {
  id: string;
  state?: string;
  type?: string;
  capabilities?: string[];
  max_context_length?: number | null;
  loaded_context_length?: number | null;
};

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

function formatModelPrice(model: AIModel): string {
  if (isLocalAIModelId(model.model_id)) return "Local";
  return formatUsdPerToken(model.combined_cost_per_million);
}

function formatBalanceUsd(value?: string | null): string {
  if (value == null || value === "") return "$--.--";
  const numeric = Number.parseFloat(value ?? "");
  if (!Number.isFinite(numeric)) return "$--.--";
  return `$${numeric.toFixed(2)}`;
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

function clampContextLength(value: number): number {
  if (!Number.isFinite(value)) return 4096;
  return Math.min(
    Math.max(Math.round(value), LOCAL_CONTEXT_MIN),
    LOCAL_CONTEXT_MAX,
  );
}

function getLocalAIStatusBadge(
  status: LocalAIStatus,
  checking: boolean,
  modelId: string,
) {
  if (checking) {
    return {
      label: "Checking",
      className: "border-sky-300/22 bg-sky-400/10 text-sky-100",
    };
  }

  if (!status?.reachable) {
    return {
      label: "Offline",
      className: "border-amber-300/24 bg-amber-400/12 text-amber-100",
    };
  }

  const runtimeModelId = stripLocalModelPrefix(modelId);
  if (
    status.matching_model_loaded &&
    status.runtime_model_id &&
    modelIdsMatch(status.runtime_model_id, runtimeModelId)
  ) {
    return {
      label: "Ready",
      className: "border-emerald-300/28 bg-emerald-300/16 text-emerald-50",
    };
  }

  if (!status.models.some((loadedModelId) => modelIdsMatch(loadedModelId, runtimeModelId))) {
    return {
      label: "Auto load",
      className: "border-amber-300/24 bg-amber-400/12 text-amber-100",
    };
  }

  return {
    label: "Ready",
    className: "border-emerald-300/28 bg-emerald-300/16 text-emerald-50",
  };
}

function stripLocalModelPrefix(modelId: string): string {
  return modelId.startsWith("lmstudio/") ? modelId.slice("lmstudio/".length) : modelId;
}

function modelIdsMatch(left: string, right: string): boolean {
  const normalizedLeft = left.toLowerCase();
  const normalizedRight = right.toLowerCase();
  return (
    normalizedLeft === normalizedRight ||
    normalizedLeft.endsWith(`/${normalizedRight}`) ||
    normalizedRight.endsWith(`/${normalizedLeft}`)
  );
}

function isUsableLocalRuntimeModel(model: LocalAIAvailableModel): boolean {
  const type = model.type?.toLowerCase();
  if (type && type !== "llm" && type !== "vlm") return false;

  const capabilities = model.capabilities ?? [];
  if (capabilities.length === 0) return true;

  return capabilities.some((capability) => {
    const normalized = capability.toLowerCase().replaceAll("-", "_");
    return normalized === "tool_use" || normalized === "tools";
  });
}

function formatLocalRuntimeDisplayName(runtimeModelId: string): string {
  const tail = runtimeModelId.split("/").at(-1) ?? runtimeModelId;
  return tail
    .replaceAll("_", "-")
    .split("-")
    .filter(Boolean)
    .map((part) => {
      if (part.length <= 3 || /\d/.test(part)) return part.toUpperCase();
      return `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`;
    })
    .join(" ");
}

function buildLocalRuntimeModels(status: LocalAIStatus): AIModel[] {
  if (!status?.reachable) return [];

  const seen = new Set<string>();
  return status.available_models
    .filter(isUsableLocalRuntimeModel)
    .filter((runtimeModel) => {
      const normalizedId = runtimeModel.id.toLowerCase();
      if (seen.has(normalizedId)) return false;
      seen.add(normalizedId);
      return true;
    })
    .map((runtimeModel, index) => {
      const modelId = `lmstudio/${runtimeModel.id}`;
      const contextWindow =
        runtimeModel.max_context_length ??
        runtimeModel.loaded_context_length ??
        status.loaded_context_length ??
        32768;
      return {
        id: -100000 - index,
        provider: "lmstudio",
        model_id: modelId,
        display_name: formatLocalRuntimeDisplayName(runtimeModel.id),
        description:
          "Local offline opponent loaded from LM Studio before its AI turn. Charges no credits.",
        quality_tier: "standard",
        cost_per_game: "0.00",
        pricing: {},
        context_window: contextWindow,
        max_tokens: null,
        input_cost_per_million: "0",
        output_cost_per_million: "0",
        cache_read_cost_per_million: "0",
        cache_write_cost_per_million: "0",
        combined_cost_per_million: "0",
        is_flagship: false,
      };
    });
}

function handleSelectKeyDown(
  event: ReactKeyboardEvent<HTMLElement>,
  onSelect: () => void,
) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  onSelect();
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

function LocalAIRuntimePanel({
  contextLength,
  reloadAfterTurn,
  onContextLengthChange,
  onReloadAfterTurnChange,
}: {
  contextLength: number;
  reloadAfterTurn: boolean;
  onContextLengthChange: (tokens: number) => void;
  onReloadAfterTurnChange: (enabled: boolean) => void;
}) {
  const normalizedContextLength = clampContextLength(contextLength);

  return (
    <SettingsPanel
      title="LM Studio Runtime"
      description="Applied before each local AI turn."
      className="border-emerald-300/12"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <div className="min-w-0">
          <label
            htmlFor="local-ai-context-length"
            className="text-[0.78rem] font-semibold uppercase tracking-[0.2em] text-emerald-100/80"
          >
            Context window
          </label>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              id="local-ai-context-length"
              type="number"
              inputMode="numeric"
              min={LOCAL_CONTEXT_MIN}
              max={LOCAL_CONTEXT_MAX}
              step={128}
              value={normalizedContextLength}
              onChange={(event) =>
                onContextLengthChange(clampContextLength(Number(event.target.value)))
              }
              className="h-11 w-32 rounded-[0.9rem] border border-emerald-300/22 bg-emerald-950/30 px-3 font-mono text-sm font-semibold text-emerald-50 outline-none transition-colors focus:border-emerald-200/54"
            />
            <div className="flex flex-wrap gap-2">
              {LOCAL_CONTEXT_PRESETS.map((preset) => {
                const isSelected = normalizedContextLength === preset;
                return (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => onContextLengthChange(preset)}
                    className={`rounded-full border px-3 py-1.5 text-[0.74rem] font-semibold uppercase tracking-[0.14em] transition-colors ${
                      isSelected
                        ? "border-emerald-200/46 bg-emerald-300/18 text-emerald-50"
                        : "border-white/10 bg-white/5 text-stone-300 hover:border-emerald-300/28 hover:text-emerald-100"
                    }`}
                  >
                    {preset}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={reloadAfterTurn}
          onClick={() => onReloadAfterTurnChange(!reloadAfterTurn)}
          className={`flex min-w-[13rem] items-center justify-between gap-4 rounded-[1.1rem] border px-4 py-3 text-left transition-colors ${
            reloadAfterTurn
              ? "border-emerald-200/34 bg-emerald-300/14 text-emerald-50"
              : "border-white/10 bg-stone-950/72 text-stone-300 hover:border-emerald-300/24"
          }`}
        >
          <span className="text-[0.82rem] font-semibold uppercase tracking-[0.16em]">
            Reload after turn
          </span>
          <span
            className={`relative h-6 w-11 rounded-full border transition-colors ${
              reloadAfterTurn
                ? "border-emerald-200/42 bg-emerald-400/28"
                : "border-white/12 bg-black/40"
            }`}
          >
            <span
              className={`absolute top-1 h-4 w-4 rounded-full bg-white shadow-[0_4px_12px_rgba(0,0,0,0.28)] transition-transform ${
                reloadAfterTurn ? "translate-x-5" : "translate-x-1"
              }`}
            />
          </span>
        </button>
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
  const creditBalance = useGameStore((s) => s.creditBalance);
  const setCreditBalance = useGameStore((s) => s.setCreditBalance);
  const selectedModelId = useGameStore((s) => s.selectedModelId);
  const setSelectedModelId = useGameStore((s) => s.setSelectedModelId);
  const aiTimeout = useGameStore((s) => s.aiTimeout);
  const setAITimeout = useGameStore((s) => s.setAITimeout);
  const aiMaxSteps = useGameStore((s) => s.aiMaxSteps);
  const setAIMaxSteps = useGameStore((s) => s.setAIMaxSteps);
  const localAIContextLength = useGameStore((s) => s.localAIContextLength);
  const setLocalAIContextLength = useGameStore((s) => s.setLocalAIContextLength);
  const localAIReloadAfterTurn = useGameStore((s) => s.localAIReloadAfterTurn);
  const setLocalAIReloadAfterTurn = useGameStore(
    (s) => s.setLocalAIReloadAfterTurn,
  );
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
  const [modelsExpanded, setModelsExpanded] = useState(false);
  const [localAIStatus, setLocalAIStatus] = useState<LocalAIStatus>(null);
  const [checkingLocalAIStatus, setCheckingLocalAIStatus] = useState(false);
  const rivalSectionRef = useRef<HTMLElement | null>(null);

  const refreshLocalAIStatus = useCallback(async (modelId?: string) => {
    const targetModelId = modelId ?? LOCAL_AI_AUTO_MODEL_ID;
    setCheckingLocalAIStatus(true);
    try {
      const result = (await fetch(
        `/api/ai/local/status?model=${encodeURIComponent(targetModelId)}`,
        { cache: "no-store" },
      ).then((response) => response.json())) as LocalAIStatus;
      setLocalAIStatus(result);
    } catch {
      setLocalAIStatus({
        ok: false,
        reachable: false,
        base_url: "http://localhost:1234/v1",
        model_id: targetModelId,
        runtime_model_id: null,
        loaded_context_length: null,
        matching_model_loaded: false,
        models: [],
        available_models: [],
        error: "LM Studio status check failed.",
      });
    } finally {
      setCheckingLocalAIStatus(false);
    }
  }, []);

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

        let nextSelectedModelId = localSelectedModelId;

        if (profileResult.profile) {
          setCreditBalance(profileResult.profile.credit_balance);
          if (
            profileResult.profile.preferred_ai_model_id &&
            (isLocalAIModelId(profileResult.profile.preferred_ai_model_id) ||
              nextModels.some(
                (model) =>
                  model.model_id === profileResult.profile.preferred_ai_model_id,
              ))
          ) {
            nextSelectedModelId = profileResult.profile.preferred_ai_model_id;
          }
        } else if (token) {
          setNotice({
            tone: "info",
            text: "Account sync is unavailable right now. Settings still work locally on this device.",
          });
        }

        if (nextSelectedModelId !== localSelectedModelId) {
          setSelectedModelId(nextSelectedModelId);
        }

        if (
          nextModels.length > 0 &&
          !nextModels.some((model) => model.model_id === nextSelectedModelId) &&
          !isLocalAIModelId(nextSelectedModelId)
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

  useEffect(() => {
    void refreshLocalAIStatus(
      isLocalAIModelId(selectedModelId) ? selectedModelId : LOCAL_AI_AUTO_MODEL_ID,
    );
  }, [selectedModelId, refreshLocalAIStatus]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const focusRival =
      new URLSearchParams(window.location.search).get("focus") === "rival";
    if (!focusRival) return;
    setModelsExpanded(true);
    const frame = window.requestAnimationFrame(() => {
      rivalSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const localRuntimeModels = useMemo(
    () => buildLocalRuntimeModels(localAIStatus),
    [localAIStatus],
  );
  const localRuntimeModelIds = useMemo(
    () => localRuntimeModels.map((model) => model.model_id),
    [localRuntimeModels],
  );
  const localRuntimeModelIdSet = useMemo(
    () => new Set(localRuntimeModelIds),
    [localRuntimeModelIds],
  );

  useEffect(() => {
    if (localRuntimeModelIds.length === 0) return;
    if (
      selectedModelId === LOCAL_AI_AUTO_MODEL_ID ||
      (isLocalAIModelId(selectedModelId) &&
        !localRuntimeModelIdSet.has(selectedModelId))
    ) {
      setSelectedModelId(localRuntimeModelIds[0]);
    }
  }, [
    localRuntimeModelIdSet,
    localRuntimeModelIds,
    selectedModelId,
    setSelectedModelId,
  ]);

  const catalogModels = models.filter((model) => {
    if (!isLocalAIModelId(model.model_id)) return true;
    return localRuntimeModels.length === 0 && model.model_id !== LOCAL_AI_AUTO_MODEL_ID;
  });
  const selectableModels = [...localRuntimeModels, ...catalogModels];
  const selectedModel =
    selectableModels.find((model) => model.model_id === selectedModelId) ??
    selectableModels[0] ??
    null;
  const selectedModelIsLocal = isLocalAIModelId(
    selectedModel?.model_id ?? selectedModelId,
  );
  const displayedModels = [...selectableModels].sort((left, right) => {
    const localDiff =
      Number(isLocalAIModelId(right.model_id)) -
      Number(isLocalAIModelId(left.model_id));
    if (localDiff !== 0) return localDiff;

    const priceDiff =
      Number.parseFloat(right.combined_cost_per_million) -
      Number.parseFloat(left.combined_cost_per_million);
    if (Number.isFinite(priceDiff) && priceDiff !== 0) return priceDiff;

    const contextDiff = (right.context_window ?? 0) - (left.context_window ?? 0);
    if (contextDiff !== 0) return contextDiff;

    return left.display_name.localeCompare(right.display_name);
  });
  const maxContextWindow = Math.max(
    1,
    ...displayedModels.map((model) => model.context_window ?? 0),
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

    const previousModelId = selectedModelId;
    const chosenModel = selectableModels.find((model) => model.model_id === modelId);

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

  function handleTopUpCredit() {
    setNotice({
      tone: "info",
      text: "Top-up checkout lands next. The live credit countdown is already wired into the game now.",
    });
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
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start xl:grid-cols-[minmax(0,1fr)_360px]">
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

            <motion.section
              whileHover={{ y: -2, scale: 1.004 }}
              className="relative overflow-hidden rounded-[1.8rem] border border-amber-300/20 p-4 shadow-[0_20px_55px_rgba(0,0,0,0.30)] transition-[border-color,box-shadow,transform] duration-300 hover:border-amber-200/28 hover:shadow-[0_24px_60px_rgba(0,0,0,0.34)] lg:w-[340px] lg:justify-self-end xl:w-[360px]"
              style={PREMIUM_CREDIT_PANEL_STYLE}
              onMouseMove={handlePremiumSurfacePointer}
            >
              <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/70 to-transparent" />
              <div className="relative flex items-end justify-between gap-4">
                <div className="order-1">
                  <motion.button
                    type="button"
                  whileHover={{ y: -1.5 }}
                  whileTap={{ scale: 0.985 }}
                  onClick={handleTopUpCredit}
                    className="group relative overflow-hidden rounded-full border border-amber-100/46 bg-[linear-gradient(135deg,rgba(251,191,36,0.32),rgba(245,158,11,0.18))] px-4 py-2.5 shadow-[0_18px_38px_rgba(251,191,36,0.18),0_0_38px_rgba(251,191,36,0.12)] transition-[border-color,box-shadow,transform,filter] duration-300 hover:border-amber-50/70 hover:shadow-[0_22px_44px_rgba(251,191,36,0.26),0_0_44px_rgba(251,191,36,0.18)]"
                  >
                    <span className="pointer-events-none absolute inset-0 bg-[linear-gradient(120deg,transparent,rgba(255,255,255,0.18),transparent)] opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                    <span className="font-gold-money text-[1.04rem] font-black leading-none">
                      Top up balance
                    </span>
                  </motion.button>
                </div>

                <div className="order-2 text-right">
                  <div className="text-[0.68rem] uppercase tracking-[0.3em] text-amber-100/65">
                    Balance
                  </div>
                  <motion.div
                    whileHover={{ scale: 1.015 }}
                    className="font-gold-shiny mt-2 text-4xl font-black leading-none sm:text-5xl"
                  >
                      {formatBalanceUsd(creditBalance)}
                  </motion.div>
                </div>
              </div>
            </motion.section>
          </div>
        </div>

        <div className="ornate-scrollbar relative flex-1 min-h-0 overflow-y-auto p-4 sm:p-5">
          <div className="flex min-h-0 flex-col gap-4">
            <section ref={rivalSectionRef} className="min-h-0">
              <div className="flex min-h-0 flex-col">
                <div className="pb-4">
                  <motion.button
                    type="button"
                    whileHover={{ y: -1.5 }}
                    whileTap={{ scale: 0.995 }}
                    onClick={() => setModelsExpanded((current) => !current)}
                    className={`group relative flex w-full items-center justify-between gap-4 rounded-[1.6rem] border px-4 py-4 text-left shadow-[0_16px_40px_rgba(0,0,0,0.2)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:shadow-[0_20px_45px_rgba(0,0,0,0.24)] ${
                      selectedModelIsLocal
                        ? "border-emerald-300/16 bg-[linear-gradient(180deg,rgba(10,33,25,0.72),rgba(8,18,14,0.84))] hover:border-emerald-200/28"
                        : "border-white/8 bg-[linear-gradient(180deg,rgba(17,14,11,0.76),rgba(11,9,8,0.82))] hover:border-amber-200/24"
                    }`}
                    onMouseMove={handlePremiumSurfacePointer}
                    style={PREMIUM_PANEL_STYLE}
                    aria-expanded={modelsExpanded}
                    aria-controls="settings-model-table"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-3">
                        <span className="text-[1.65rem] sm:text-[1.9rem]">🧠</span>
                        <span className="font-gold-shiny text-3xl font-black tracking-tight sm:text-[2.35rem]">
                          Choose the rival
                        </span>
                      </div>
                      <div className="mt-2 min-w-0 pl-[2.7rem]">
                        <div
                          className={`truncate text-[1.35rem] font-black sm:text-[1.55rem] ${
                            selectedModelIsLocal
                              ? "text-emerald-100"
                              : "font-gold-shiny"
                          }`}
                        >
                          {selectedModel?.display_name ?? "No rival selected"}
                        </div>
                      </div>
                    </div>

                    <motion.div
                      animate={{ rotate: modelsExpanded ? 180 : 0 }}
                      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                      className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full border bg-white/5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] ${
                        selectedModelIsLocal
                          ? "border-emerald-300/22 text-emerald-100"
                          : "border-amber-300/18 text-amber-100"
                      }`}
                    >
                      <svg
                        viewBox="0 0 24 24"
                        className="h-5 w-5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <path d="m6 9 6 6 6-6" />
                      </svg>
                    </motion.div>
                  </motion.button>

                  {savingModelId && (
                    <div className="mt-3 inline-flex rounded-full border border-amber-300/20 bg-amber-400/10 px-3 py-1.5 text-xs font-medium text-amber-100 shadow-[0_10px_24px_rgba(251,191,36,0.08)]">
                      Updating {savingModelId}...
                    </div>
                  )}

                  {selectedModelIsLocal ? (
                    <div className="mt-3">
                      <LocalAIRuntimePanel
                        contextLength={localAIContextLength}
                        reloadAfterTurn={localAIReloadAfterTurn}
                        onContextLengthChange={setLocalAIContextLength}
                        onReloadAfterTurnChange={setLocalAIReloadAfterTurn}
                      />
                    </div>
                  ) : null}
                </div>

                <AnimatePresence initial={false}>
                  {modelsExpanded ? (
                    <motion.div
                      key="models-panel"
                      id="settings-model-table"
                      initial={{ height: 0, opacity: 0, y: -10 }}
                      animate={{ height: "auto", opacity: 1, y: 0 }}
                      exit={{ height: 0, opacity: 0, y: -10 }}
                      transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
                      className="overflow-hidden"
                    >
                      <div className="pt-1">
                        {loading ? (
                          <div
                            className="relative overflow-hidden rounded-[1.85rem] border border-white/8 shadow-[0_18px_45px_rgba(0,0,0,0.24)]"
                            style={PREMIUM_PANEL_STYLE}
                            onMouseMove={handlePremiumSurfacePointer}
                          >
                            <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/12 to-transparent" />
                            <div className="border-b border-white/8 px-4 py-3">
                              <div className="h-4 w-40 animate-pulse rounded-full bg-white/8" />
                            </div>
                            <div className="space-y-2 p-3">
                              {Array.from({ length: 7 }).map((_, index) => (
                                <div
                                  key={index}
                                  className="grid animate-pulse grid-cols-[minmax(0,1fr)_110px_110px] gap-3 rounded-[1.2rem] border border-white/6 bg-black/12 px-3 py-3"
                                >
                                  <div className="space-y-2">
                                    <div className="h-4 w-40 rounded-full bg-white/8" />
                                    <div className="h-3 w-64 rounded-full bg-white/6" />
                                  </div>
                                  <div className="h-4 w-20 justify-self-end rounded-full bg-white/8" />
                                  <div className="h-4 w-20 justify-self-end rounded-full bg-white/8" />
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : selectableModels.length > 0 ? (
                          <div
                            className="relative overflow-hidden rounded-[1.85rem] border border-white/8 shadow-[0_18px_45px_rgba(0,0,0,0.24)]"
                            style={PREMIUM_PANEL_STYLE}
                            onMouseMove={handlePremiumSurfacePointer}
                          >
                            <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/12 to-transparent" />
                            <div className="ornate-scrollbar overflow-x-auto">
                              <table className="min-w-[720px] w-full border-separate border-spacing-0">
                                <thead className="sticky top-0 z-10 backdrop-blur-xl">
                                  <tr className="bg-[linear-gradient(180deg,rgba(22,19,16,0.98),rgba(15,12,10,0.94))] text-left">
                                    <th className="border-b border-white/8 px-4 py-3 text-[0.78rem] uppercase tracking-[0.24em] text-stone-400">
                                      Model
                                    </th>
                                    <th className="border-b border-white/8 px-4 py-3 text-right text-[0.78rem] uppercase tracking-[0.24em] text-stone-400">
                                      Context
                                    </th>
                                    <th className="border-b border-white/8 px-4 py-3 text-right text-[0.78rem] uppercase tracking-[0.24em] text-stone-400">
                                      $ / Price
                                    </th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {displayedModels.map((model) => {
                                    const isSelected = selectedModelId === model.model_id;
                                    const isSaving = savingModelId === model.model_id;
                                    const isLocal = isLocalAIModelId(model.model_id);
                                    const localStatusBadge = getLocalAIStatusBadge(
                                      localAIStatus,
                                      checkingLocalAIStatus,
                                      model.model_id,
                                    );
                                    const selectedCellStyle = isLocal
                                      ? SELECTED_LOCAL_ROW_CELL_STYLE
                                      : SELECTED_ROW_CELL_STYLE;
                                    const rowBackgroundClass = isSelected
                                      ? isLocal
                                        ? "bg-[linear-gradient(90deg,rgba(16,185,129,0.20),rgba(16,185,129,0.08)_46%,rgba(16,185,129,0.03))]"
                                        : "bg-[linear-gradient(90deg,rgba(251,191,36,0.12),rgba(251,191,36,0.03)_42%,transparent)]"
                                      : isLocal
                                        ? "bg-[linear-gradient(90deg,rgba(16,185,129,0.07),rgba(16,185,129,0.025)_48%,transparent)] hover:bg-emerald-400/[0.065]"
                                        : "hover:bg-white/[0.035]";
                                    const focusBorderClass = isLocal
                                      ? "group-focus-visible:border-emerald-300/30"
                                      : "group-focus-visible:border-amber-300/24";
                                    const idleBorderClass = isLocal
                                      ? "border-b border-emerald-300/12 group-hover:border-emerald-300/26"
                                      : "border-b border-white/6 group-hover:border-amber-300/14";
                                    const selectedLeftCellClass = isLocal
                                      ? "border-y border-l border-emerald-300/52 shadow-[inset_0_0_0_1px_rgba(16,185,129,0.22)]"
                                      : "border-y border-l border-amber-300/44 shadow-[inset_0_0_0_1px_rgba(251,191,36,0.18)]";
                                    const selectedMiddleCellClass = isLocal
                                      ? "border-y border-emerald-300/52 shadow-[inset_0_0_0_1px_rgba(16,185,129,0.22)]"
                                      : "border-y border-amber-300/44 shadow-[inset_0_0_0_1px_rgba(251,191,36,0.18)]";
                                    const selectedRightCellClass = isLocal
                                      ? "border-y border-r border-emerald-300/52 shadow-[inset_0_0_0_1px_rgba(16,185,129,0.22)]"
                                      : "border-y border-r border-amber-300/44 shadow-[inset_0_0_0_1px_rgba(251,191,36,0.18)]";
                                    const selectedTextClass = isLocal
                                      ? "text-emerald-50"
                                      : "text-amber-100";
                                    const contextShare =
                                      model.context_window && maxContextWindow > 0
                                        ? Math.max(
                                            10,
                                            Math.round((model.context_window / maxContextWindow) * 100),
                                          )
                                        : 0;

                                    return (
                                      <tr
                                        key={model.model_id}
                                        tabIndex={savingModelId ? -1 : 0}
                                        role="button"
                                        aria-disabled={Boolean(savingModelId)}
                                        aria-pressed={isSelected}
                                        onMouseMove={handlePremiumSurfacePointer}
                                        onClick={() => void persistModelSelection(model.model_id)}
                                        onKeyDown={(event) =>
                                          handleSelectKeyDown(event, () => {
                                            void persistModelSelection(model.model_id);
                                          })
                                        }
                                        className={`group cursor-pointer outline-none transition-[background-color,box-shadow,transform] duration-300 ${rowBackgroundClass} ${savingModelId ? "pointer-events-none opacity-75" : ""}`}
                                      >
                                        <td
                                          className={`px-4 py-5 align-top transition-[border-color,box-shadow,background-color] duration-300 ${focusBorderClass} ${
                                            isSelected
                                              ? selectedLeftCellClass
                                              : idleBorderClass
                                          } rounded-l-[1.35rem]`}
                                          style={isSelected ? selectedCellStyle : undefined}
                                        >
                                          <div className="flex min-w-0 items-start gap-3">
                                            <div
                                              className={`mt-0.5 flex h-12 w-12 shrink-0 items-center justify-center rounded-[1rem] border font-black shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] ${
                                                isLocal ? "text-[1rem] tracking-[0.08em]" : "text-[1.75rem]"
                                              } ${
                                                isSelected
                                                  ? isLocal
                                                    ? "border-emerald-200/42 bg-emerald-300/18 text-emerald-50"
                                                    : "border-amber-300/28 bg-amber-200/8"
                                                  : isLocal
                                                    ? "border-emerald-300/20 bg-emerald-950/42 text-emerald-100"
                                                    : "border-white/10 bg-stone-950/78"
                                              }`}
                                            >
                                              {PROVIDER_ICONS[model.provider] || "🔧"}
                                            </div>
                                            <div className="min-w-0 flex-1">
                                              <div className="flex flex-wrap items-center gap-2">
                                                <div className="truncate text-[1.3rem] font-black sm:text-[1.38rem]">
                                                  <span
                                                    className={
                                                      isLocal
                                                        ? isSelected
                                                          ? "text-emerald-50"
                                                          : "text-emerald-200"
                                                        : isSelected
                                                          ? "font-gold-shiny"
                                                          : "font-gold-dark"
                                                    }
                                                  >
                                                    {model.display_name}
                                                  </span>
                                                </div>
                                                {isLocal ? (
                                                  <>
                                                    <span className="rounded-full border border-emerald-300/26 bg-emerald-300/14 px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-emerald-50">
                                                      Free
                                                    </span>
                                                    <span
                                                      className={`rounded-full border px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] ${localStatusBadge.className}`}
                                                    >
                                                      {localStatusBadge.label}
                                                    </span>
                                                  </>
                                                ) : (
                                                  <span
                                                    className={`rounded-full px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] ${
                                                      QUALITY_COLORS[model.quality_tier] ||
                                                      QUALITY_COLORS.standard
                                                    }`}
                                                  >
                                                    {model.quality_tier}
                                                  </span>
                                                )}
                                                {model.is_flagship && (
                                                  <span className="rounded-full border border-amber-300/20 bg-amber-400/12 px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-amber-100">
                                                    Flagship
                                                  </span>
                                                )}
                                                {(isSaving || isSelected) && (
                                                  <span
                                                    className={`rounded-full border px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] ${
                                                      isSaving
                                                        ? "border-sky-400/24 bg-sky-400/12 text-sky-100"
                                                        : isLocal
                                                          ? "border-emerald-200/34 bg-emerald-300/18 text-emerald-50"
                                                          : "border-amber-300/24 bg-amber-300/12 text-amber-100"
                                                    }`}
                                                  >
                                                    {isSaving ? "Saving" : "Active"}
                                                  </span>
                                                )}
                                              </div>
                                              <div className="mt-1 break-all font-mono text-[0.82rem] text-stone-500">
                                                {model.model_id}
                                              </div>
                                              {model.description && (
                                                <p className="mt-2 hidden max-w-3xl text-[1.1rem] leading-9 text-stone-50/95 md:block">
                                                  {model.description}
                                                </p>
                                              )}
                                            </div>
                                          </div>
                                        </td>
                                        <td
                                          className={`px-4 py-5 text-right align-middle transition-[border-color,box-shadow,background-color] duration-300 ${
                                            isSelected
                                              ? selectedMiddleCellClass
                                              : idleBorderClass
                                          }`}
                                          style={isSelected ? selectedCellStyle : undefined}
                                        >
                                          <div className="ml-auto flex w-[220px] items-center gap-4 sm:w-[260px]">
                                            <div className="relative h-3.5 flex-1 overflow-hidden rounded-full border border-white/8 bg-black/68 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                                              <div
                                                className={`absolute inset-y-0 left-0 rounded-full ${
                                                  isSelected
                                                    ? isLocal
                                                      ? "bg-[linear-gradient(90deg,rgba(110,231,183,0.82),rgba(16,185,129,0.82))] shadow-[0_0_12px_rgba(16,185,129,0.20)]"
                                                      : "bg-[linear-gradient(90deg,rgba(252,211,77,0.72),rgba(245,158,11,0.74))] shadow-[0_0_12px_rgba(251,191,36,0.18)]"
                                                    : isLocal
                                                      ? "bg-[linear-gradient(90deg,rgba(110,231,183,0.42),rgba(16,185,129,0.58))]"
                                                      : "bg-[linear-gradient(90deg,rgba(255,255,255,0.26),rgba(245,158,11,0.52))]"
                                                }`}
                                                style={{ width: `${contextShare}%` }}
                                              />
                                            </div>
                                            <div
                                              className={`w-16 text-right text-base font-semibold sm:text-[1.15rem] ${
                                                isSelected ? selectedTextClass : isLocal ? "text-emerald-100" : "text-stone-100"
                                              }`}
                                            >
                                              {formatContextWindow(model.context_window)}
                                            </div>
                                          </div>
                                        </td>
                                        <td
                                          className={`px-4 py-5 text-right align-middle transition-[border-color,box-shadow,background-color] duration-300 ${
                                            isSelected
                                              ? selectedRightCellClass
                                              : idleBorderClass
                                          } rounded-r-[1.35rem]`}
                                          style={isSelected ? selectedCellStyle : undefined}
                                        >
                                          <div
                                            className={`text-base font-semibold sm:text-[1.15rem] ${
                                              isSelected ? selectedTextClass : isLocal ? "text-emerald-100" : "text-stone-100"
                                            }`}
                                          >
                                            {formatModelPrice(model)}
                                          </div>
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        ) : (
                          <div
                            className="rounded-[1.7rem] border border-white/8 p-5 text-sm text-stone-400 shadow-[0_16px_40px_rgba(0,0,0,0.20)]"
                            style={PREMIUM_PANEL_STYLE}
                            onMouseMove={handlePremiumSurfacePointer}
                          >
                            No synced models are available yet. Run{" "}
                            <span className="font-mono text-stone-200">
                              python manage.py sync_gateway_models
                            </span>{" "}
                            first.
                          </div>
                        )}
                      </div>
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </div>
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
