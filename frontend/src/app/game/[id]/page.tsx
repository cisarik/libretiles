"use client";

import { useEffect, useCallback, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragOverEvent,
  DragStartEvent,
  PointerSensor,
  TouchSensor,
  defaultDropAnimation,
  defaultDropAnimationSideEffects,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import confetti from "canvas-confetti";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";

import { Board } from "@/components/board/Board";
import { TileRack } from "@/components/tiles/TileRack";
import { ScorePanel } from "@/components/game/ScorePanel";
import { GameControls } from "@/components/game/GameControls";
import { BlankPicker } from "@/components/game/BlankPicker";
import { AIThinkingOverlay } from "@/components/game/AIThinkingOverlay";
import { ChatPanel } from "@/components/game/ChatPanel";
import { ProfileModal } from "@/components/game/ProfileModal";
import { GameHistoryModal } from "@/components/game/GameHistoryModal";
import { PromptCatalogModal } from "@/components/game/PromptCatalogModal";
import { PromptPreviewModal } from "@/components/game/PromptPreviewModal";
import { TurnStatusNotice } from "@/components/game/TurnStatusNotice";
import { useGameStore, type BoardTheme } from "@/hooks/useGameStore";
import { useIsCoarsePointer } from "@/hooks/useIsCoarsePointer";
import {
  aiMoveRequestBody,
  buildFallbackQueue,
  fallbackQueueForCatalogFailure,
  orchestrateFallbackTurn,
  providerBadgeLabel,
} from "@/lib/ai-fallback";
import { consumeAIStream } from "@/lib/ai-move-stream";
import { api, readAiTurnTelemetry } from "@/lib/api";
import { PREMIUM_FOOTER_STYLE, handlePremiumSurfacePointer } from "@/lib/premiumSurface";
import { isPlausibleRack } from "@/lib/rack";
import { buildGameWebSocketUrl } from "@/lib/ws";
import type {
  AIPrompt,
  GameHistoryFilter,
  GameHistoryItem,
  GameHistoryResponse,
  GameHistorySort,
  GameState,
  MoveResult,
  MoveValidationResult,
  UserProfile,
  WSTicketResponse,
} from "@/lib/types";
import { Tile } from "@/components/tiles/Tile";

type RackDragData = {
  letter: string;
  index: number;
  origin: "rack";
};

type DragPreviewTarget = {
  row: number;
  col: number;
};

function isHtmlResponse(body: string, contentType: string | null) {
  return contentType?.includes("text/html") === true || /<!doctype html|<html/i.test(body);
}

async function getStreamStartError(response: Response) {
  const raw = await response.text();

  try {
    const parsed = JSON.parse(raw) as { error?: string; message?: string; detail?: string };
    return parsed.error || parsed.message || parsed.detail || `AI route failed (${response.status}).`;
  } catch {
    if (isHtmlResponse(raw, response.headers.get("content-type"))) {
      return `AI route failed (${response.status}) before the stream started.`;
    }

    const preview = raw.replace(/\s+/g, " ").trim().slice(0, 220);
    return preview
      ? `AI route failed (${response.status}): ${preview}`
      : `AI route failed (${response.status}).`;
  }
}

// ---------- Toast types ----------
type Toast = {
  id: string;
  type: "invalid_word" | "placement_error" | "ai_pass" | "ai_played" | "error" | "success";
  message: string;
  words?: string[];
  score?: number;
};

type AIBlockerModal = {
  kind: "provider_auth_failed" | "provider_rate_limited" | "provider_unavailable";
  title: string;
  message: string;
};

const THEME_FRAME_BORDER: Record<BoardTheme, string> = {
  wood: "rgba(123, 90, 47, 0.56)",
  black: "rgba(131, 101, 58, 0.42)",
  green: "rgba(87, 111, 86, 0.44)",
};

function humanizeModelId(modelId?: string | null): string | null {
  if (!modelId) return null;
  const base = modelId.split("/").pop() ?? modelId;
  return base
    .split(/[-_]+/)
    .filter(Boolean)
    .map((part) => {
      if (/^[0-9.]+$/.test(part)) return part;
      if (part.length <= 3) return part.toUpperCase();
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join(" ");
}

function normalizeAIBlocker(
  message: string,
  code?: string,
): AIBlockerModal | null {
  const normalized = message.toLowerCase();

  if (
    code === "provider_auth_failed" ||
    normalized.includes("authentication failed") ||
    normalized.includes("invalid api key") ||
    normalized.includes("unauthorized")
  ) {
    return {
      kind: "provider_auth_failed",
      title: "Rival authentication failed",
      message:
        "This free rival could not authenticate. Switch to another free rival or retry later.",
    };
  }

  if (
    code === "provider_rate_limited" ||
    normalized.includes("rate limit") ||
    normalized.includes("too many requests")
  ) {
    return {
      kind: "provider_rate_limited",
      title: "Rival is rate limited",
      message:
        "This free rival is rate limited. Switch to another free rival or retry later.",
    };
  }

  if (
    code === "provider_unavailable" ||
    normalized.includes("temporarily unavailable") ||
    normalized.includes("insufficient funds")
  ) {
    return {
      kind: "provider_unavailable",
      title: "Rival is unavailable",
      message:
        "This free rival is temporarily unavailable. Switch to another free rival or retry later.",
    };
  }

  return null;
}

function ToastOverlay({ toast, onDone }: { toast: Toast; onDone: () => void }) {
  const lexiconId = useGameStore((s) => s.gameState?.lexicon_id);
  useEffect(() => {
    const t = setTimeout(onDone, toast.type === "ai_played" ? 4600 : toast.type === "ai_pass" ? 4200 : 3200);
    return () => clearTimeout(t);
  }, [toast, onDone]);

  if (toast.type === "invalid_word") {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.7, y: 40 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.8, y: -20 }}
        transition={{ type: "spring", stiffness: 400, damping: 22 }}
        className="fixed inset-0 z-[60] flex items-center justify-center pointer-events-none"
      >
        <div className="bg-red-950/90 backdrop-blur-xl border border-red-500/40 rounded-2xl
          p-6 shadow-2xl shadow-red-500/20 max-w-sm text-center pointer-events-auto">
          {/* Shaking X icon */}
          <motion.div
            animate={{ rotate: [0, -12, 12, -8, 8, 0] }}
            transition={{ duration: 0.5 }}
            className="text-5xl mb-3"
          >
            <svg className="w-16 h-16 mx-auto text-red-400" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <circle cx="12" cy="12" r="10" className="stroke-red-500/50" />
              <path d="M15 9l-6 6M9 9l6 6" />
            </svg>
          </motion.div>
          <motion.div
            animate={{ x: [0, -8, 8, -5, 5, 0] }}
            transition={{ duration: 0.4 }}
            className="text-red-300 font-bold text-lg mb-2"
          >
            Invalid Word{(toast.words?.length ?? 0) > 1 ? "s" : ""}!
          </motion.div>
          <div className="flex flex-wrap gap-1.5 justify-center">
            {toast.words?.map((w) => (
              <motion.span
                key={w}
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 500 }}
                className="px-3 py-1 bg-red-500/20 border border-red-400/30 rounded-lg
                  font-mono font-bold text-red-200 tracking-wider text-sm"
              >
                {w}
              </motion.span>
            ))}
          </div>
          <p className="text-red-400/60 text-xs mt-3">
            {lexiconId === "slovak"
              ? "Not in the Slovak lexicon"
              : "Not in Collins Scrabble Words 2019"}
          </p>
        </div>
      </motion.div>
    );
  }

  if (toast.type === "placement_error") {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.7, y: 40 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.8, y: -20 }}
        transition={{ type: "spring", stiffness: 400, damping: 22 }}
        className="fixed inset-0 z-[60] flex items-center justify-center pointer-events-none"
      >
        <div className="bg-amber-950/90 backdrop-blur-xl border border-amber-500/40 rounded-2xl
          p-6 shadow-2xl shadow-amber-500/20 max-w-sm text-center pointer-events-auto">
          <motion.div
            animate={{ rotate: [0, -15, 15, -10, 10, 0] }}
            transition={{ duration: 0.5 }}
          >
            <svg className="w-14 h-14 mx-auto text-amber-400 mb-3" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </motion.div>
          <motion.div
            animate={{ x: [0, -6, 6, -4, 4, 0] }}
            transition={{ duration: 0.4 }}
            className="text-amber-300 font-bold text-lg mb-2"
          >
            Invalid Placement
          </motion.div>
          <p className="text-amber-400/70 text-sm">{toast.message}</p>
        </div>
      </motion.div>
    );
  }

  if (toast.type === "ai_pass") {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.7 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.7 }}
        transition={{ type: "spring", stiffness: 350, damping: 22 }}
        className="fixed inset-0 z-[60] flex items-center justify-center pointer-events-none"
      >
        <div className="bg-sky-950/90 backdrop-blur-xl border border-sky-500/30 rounded-2xl
          p-6 shadow-2xl shadow-sky-500/15 max-w-sm text-center pointer-events-auto">
          <motion.div
            animate={{ rotate: [0, 15, -15, 10, -10, 0], y: [0, -5, 0] }}
            transition={{ duration: 0.8 }}
            className="text-5xl mb-3"
          >
            <svg className="w-16 h-16 mx-auto text-sky-400" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M9 12h6M12 3c4.97 0 9 4.03 9 9s-4.03 9-9 9-9-4.03-9-9 4.03-9 9-9z" />
            </svg>
          </motion.div>
          <motion.div
            initial={{ y: 10 }}
            animate={{ y: 0 }}
            className="text-sky-300 font-bold text-[1.34rem] mb-1"
          >
            {toast.message}
          </motion.div>
          <p className="text-sky-400/60 text-sm">
            {toast.message.toLowerCase().includes("exchanged")
              ? "AI refreshed the rack and spent the turn."
              : "Couldn't find a valid move - your turn!"}
          </p>
        </div>
      </motion.div>
    );
  }

  if (toast.type === "ai_played") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.9 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ type: "spring", stiffness: 400, damping: 25 }}
        className="fixed inset-0 z-[60] flex items-center justify-center pointer-events-none"
      >
        <div className="bg-emerald-950/90 backdrop-blur-xl border border-emerald-500/30 rounded-2xl
          p-6 shadow-2xl shadow-emerald-500/15 max-w-sm text-center pointer-events-auto">
          <motion.div
            animate={{ scale: [1, 1.2, 1] }}
            transition={{ duration: 0.5 }}
            className="text-4xl mb-3"
          >
            <svg className="w-12 h-12 mx-auto text-emerald-400" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          </motion.div>
          <div className="text-emerald-300 font-bold text-[1.36rem] leading-tight">
            AI played for <span className="text-emerald-100 text-[1.78rem] font-black">{toast.score}</span> pts
          </div>
          {toast.words && toast.words.length > 0 && (
            <div className="flex flex-wrap gap-1.5 justify-center mt-3">
              {toast.words.map((w) => (
                <span key={w} className="px-2 py-0.5 bg-emerald-500/15 border border-emerald-400/20
                  rounded-md font-mono font-bold text-emerald-200 text-[0.98rem] tracking-wider">
                  {w}
                </span>
              ))}
            </div>
          )}
        </div>
      </motion.div>
    );
  }

  if (toast.type === "success") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className="fixed bottom-8 left-1/2 z-[60] -translate-x-1/2 rounded-xl border border-emerald-300/24 bg-emerald-950/88 px-4 py-3 text-sm text-emerald-100 shadow-xl shadow-emerald-500/10 backdrop-blur"
      >
        {toast.message}
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="fixed bottom-8 left-1/2 -translate-x-1/2 z-[60] bg-stone-800/90 backdrop-blur
        border border-stone-600/30 rounded-xl px-4 py-3 shadow-xl text-stone-300 text-sm"
    >
      {toast.message}
    </motion.div>
  );
}

function AIBlockerOverlay({
  modal,
  onClose,
  onOpenSettings,
}: {
  modal: AIBlockerModal;
  onClose: () => void;
  onOpenSettings: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/52 px-4 backdrop-blur-sm"
    >
      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.94 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16, scale: 0.97 }}
        transition={{ type: "spring", stiffness: 320, damping: 26 }}
        className="w-full max-w-md rounded-[1.8rem] border border-amber-300/20 bg-[linear-gradient(180deg,rgba(28,22,16,0.98),rgba(12,10,9,0.98))] p-6 shadow-[0_30px_90px_rgba(0,0,0,0.42)]"
      >
        <div className="text-[0.68rem] uppercase tracking-[0.28em] text-amber-200/66">
          {modal.kind === "provider_auth_failed"
            ? "Authentication"
            : modal.kind === "provider_rate_limited"
              ? "Rate Limited"
              : "Unavailable"}
        </div>
        <h3 className="mt-3 text-2xl font-black tracking-tight text-stone-50">
          {modal.title}
        </h3>
        <p className="mt-3 text-sm leading-6 text-stone-300">
          {modal.message}
        </p>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm font-semibold text-stone-200 transition-all hover:border-white/16 hover:bg-white/8"
          >
            Close
          </button>
          <button
            type="button"
            onClick={onOpenSettings}
            className="rounded-full border border-amber-300/28 bg-amber-300/14 px-4 py-2 text-sm font-semibold text-amber-100 shadow-[0_10px_24px_rgba(251,191,36,0.10)] transition-all hover:border-amber-200/44 hover:bg-amber-300/18"
          >
            Open settings
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

export default function GamePage() {
  const params = useParams();
  const router = useRouter();
  const gameId = params.id as string;
  const isCoarsePointer = useIsCoarsePointer();

  const token = useGameStore((s) => s.token);
  const clearAuth = useGameStore((s) => s.clearAuth);
  const gameState = useGameStore((s) => s.gameState);
  const setGameState = useGameStore((s) => s.setGameState);
  const startingRack = useGameStore((s) => s.startingRack);
  const setStartingRack = useGameStore((s) => s.setStartingRack);
  const pendingTiles = useGameStore((s) => s.pendingTiles);
  const addPendingTile = useGameStore((s) => s.addPendingTile);
  const clearPendingTiles = useGameStore((s) => s.clearPendingTiles);
  const exchangeMode = useGameStore((s) => s.exchangeMode);
  const setExchangeMode = useGameStore((s) => s.setExchangeMode);
  const exchangeSelected = useGameStore((s) => s.exchangeSelected);
  const setLastMoveResult = useGameStore((s) => s.setLastMoveResult);
  const setAIThinking = useGameStore((s) => s.setAIThinking);
  const aiThinking = useGameStore((s) => s.aiThinking);
  const openBlankPicker = useGameStore((s) => s.openBlankPicker);
  const selectedModelId = useGameStore((s) => s.selectedModelId);
  const selectedPromptId = useGameStore((s) => s.selectedPromptId);
  const setSelectedPromptId = useGameStore((s) => s.setSelectedPromptId);
  const aiTimeout = useGameStore((s) => s.aiTimeout);
  const aiMaxSteps = useGameStore((s) => s.aiMaxSteps);
  const boardTheme = useGameStore((s) => s.boardTheme);
  const premiumLookEnabled = useGameStore((s) => s.premiumLookEnabled);
  const addAICandidate = useGameStore((s) => s.addAICandidate);
  const clearAICandidates = useGameStore((s) => s.clearAICandidates);
  const setAICountdown = useGameStore((s) => s.setAICountdown);
  const setAIStatusMessage = useGameStore((s) => s.setAIStatusMessage);
  const setAIFallbackAttempts = useGameStore((s) => s.setAIFallbackAttempts);
  const setAIFallbackActiveIndex = useGameStore(
    (s) => s.setAIFallbackActiveIndex,
  );
  const markAIFallbackFailed = useGameStore((s) => s.markAIFallbackFailed);
  const clearAIFallbackProgress = useGameStore((s) => s.clearAIFallbackProgress);
  const patchAITurnTelemetry = useGameStore((s) => s.patchAITurnTelemetry);
  const resetGameUi = useGameStore((s) => s.resetGameUi);

  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const aiInFlightRef = useRef(false);
  const multiplayerSocketRef = useRef<WebSocket | null>(null);

  const [aiApproved, setAiApproved] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [activeDragTile, setActiveDragTile] = useState<RackDragData | null>(null);
  const [dragPreviewTarget, setDragPreviewTarget] = useState<DragPreviewTarget | null>(null);
  const [selectedRackTile, setSelectedRackTile] = useState<RackDragData | null>(null);
  const [aiBlockerModal, setAIBlockerModal] = useState<AIBlockerModal | null>(null);
  const [startingNewGame, setStartingNewGame] = useState(false);
  const [givingUp, setGivingUp] = useState(false);
  const [newGameTransitioning, setNewGameTransitioning] = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [gamesModalOpen, setGamesModalOpen] = useState(false);
  const [promptsModalOpen, setPromptsModalOpen] = useState(false);
  const [promptPreview, setPromptPreview] = useState<AIPrompt | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [gameHistoryFilter, setGameHistoryFilter] = useState<GameHistoryFilter>("vs_ai");
  const [gameHistorySort, setGameHistorySort] = useState<GameHistorySort>("updated");
  const [gameHistoryData, setGameHistoryData] = useState<GameHistoryResponse | null>(null);
  const [gameHistoryLoading, setGameHistoryLoading] = useState(false);
  const [gameHistoryError, setGameHistoryError] = useState<string | null>(null);
  const [prompts, setPrompts] = useState<AIPrompt[]>([]);
  const [promptsLoading, setPromptsLoading] = useState(false);
  const [savingPromptId, setSavingPromptId] = useState<number | null>(null);

  const pointerSensor = useSensor(PointerSensor, { activationConstraint: { distance: 3 } });
  const touchSensor = useSensor(TouchSensor, {
    activationConstraint: { delay: 70, tolerance: 8 },
  });
  const sensors = useSensors(pointerSensor, touchSensor);

  const fetchState = useCallback(async () => {
    if (!token) return;
    try {
      const state = (await api.getGameState(token, gameId)) as GameState;
      setGameState(state);
      if (state.status === "waiting") {
        router.replace(`/waiting/${gameId}`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes("API error 401")) {
        resetGameUi();
        setUserProfile(null);
        clearAuth();
        return;
      }
      setToast({
        id: `state-${Date.now()}`,
        type: "error",
        message,
      });
    }
  }, [token, gameId, resetGameUi, router, setGameState, clearAuth]);

  useEffect(() => { fetchState(); }, [fetchState]);

  useEffect(() => {
    if (isPlausibleRack(gameState?.my_rack, gameState?.alphabet)) {
      setStartingRack([...gameState.my_rack]);
    }
  }, [gameState?.alphabet, gameState?.my_rack, setStartingRack]);

  useEffect(() => {
    if (!token || userProfile) return;
    api.me(token)
      .then((profile) => {
        setUserProfile(profile);
      })
      .catch(() => {});
  }, [token, userProfile]);

  useEffect(() => {
    if (!token || !gameState || !selectedModelId || gameState.game_mode !== "vs_ai") return;
    if (gameState.ai_model_id === selectedModelId) return;

    let cancelled = false;

    api
      .updateGameAIModel(token, gameId, { ai_model_model_id: selectedModelId })
      .then((result) => {
        if (cancelled || !result.ok) return;
        const latestState = useGameStore.getState().gameState;
        if (!latestState) return;
        setGameState({
          ...latestState,
          ai_model_id: result.ai_model_id,
          ai_model_display_name: result.ai_model_display_name,
        });
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [token, gameId, gameState, selectedModelId, setGameState]);

  useEffect(() => {
    if (!token || !gameState || selectedPromptId == null || gameState.game_mode !== "vs_ai") return;
    if (gameState.ai_prompt_id === selectedPromptId) return;

    let cancelled = false;
    const previousPromptId = gameState.ai_prompt_id ?? null;
    setSavingPromptId(selectedPromptId);

    api
      .updateGameAIPrompt(token, gameId, { ai_prompt_id: selectedPromptId })
      .then((result) => {
        if (cancelled || !result.ok) return;
        const latestState = useGameStore.getState().gameState;
        if (!latestState) return;
        setGameState({
          ...latestState,
          ai_prompt_id: result.ai_prompt_id,
          ai_prompt_name: result.ai_prompt_name,
          ai_prompt_fitness: result.ai_prompt_fitness,
        });
      })
      .catch(() => {
        if (!cancelled) {
          setSelectedPromptId(previousPromptId);
          setToast({
            id: `prompt-${Date.now()}`,
            type: "error",
            message: "Could not switch AI prompt right now.",
          });
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSavingPromptId((current) => (current === selectedPromptId ? null : current));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token, gameId, gameState, selectedPromptId, setGameState, setSelectedPromptId]);

  useEffect(() => {
    return () => { if (countdownRef.current) clearInterval(countdownRef.current); };
  }, []);

  const startCountdown = useCallback(
    (seconds: number) => {
      if (countdownRef.current) clearInterval(countdownRef.current);
      let remaining = seconds;
      setAICountdown(remaining);
      countdownRef.current = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          if (countdownRef.current) clearInterval(countdownRef.current);
          countdownRef.current = null;
          remaining = 0;
        }
        setAICountdown(remaining);
      }, 1000);
    },
    [setAICountdown],
  );

  const stopCountdown = useCallback(() => {
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
    setAICountdown(0);
  }, [setAICountdown]);

  const showToast = useCallback((t: Toast) => {
    setToast(t);
  }, []);

  const handleNewGame = useCallback(async () => {
    if (!token || startingNewGame) return;

    setStartingNewGame(true);
    setNewGameTransitioning(true);
    try {
      await new Promise((resolve) => window.setTimeout(resolve, 320));
      resetGameUi();
      setAiApproved(false);
      setAiError(null);
      setAIBlockerModal(null);
      router.replace("/play");
    } catch (err) {
      setNewGameTransitioning(false);
      showToast({
        id: `new-${Date.now()}`,
        type: "error",
        message: err instanceof Error ? err.message : "Could not start a new game",
      });
    } finally {
      setStartingNewGame(false);
    }
  }, [
    token,
    startingNewGame,
    resetGameUi,
    router,
    showToast,
  ]);

  const handleGiveUp = useCallback(async () => {
    if (!token || givingUp || gameState?.game_over || aiThinking) return;
    const giveUpMessage = gameState?.game_mode === "vs_ai"
      ? "Give up this game? The AI will be declared the winner."
      : "Give up this game? Your opponent will be declared the winner.";
    if (!window.confirm(giveUpMessage)) return;

    setGivingUp(true);
    try {
      const result = (await api.giveUp(token, gameId)) as MoveResult;
      if (result.ok && result.state) {
        setGameState(result.state);
        setAiApproved(false);
        setAIThinking(false);
        clearPendingTiles();
        setExchangeMode(false);
        showToast({
          id: `giveup-${Date.now()}`,
          type: "error",
          message: "You gave up the game.",
        });
        return;
      }

      showToast({
        id: `giveup-${Date.now()}`,
        type: "error",
        message: result.error ?? "Could not give up this game",
      });
    } catch (err) {
      showToast({
        id: `giveup-${Date.now()}`,
        type: "error",
        message: err instanceof Error ? err.message : "Could not give up this game",
      });
    } finally {
      setGivingUp(false);
    }
  }, [
    token,
    givingUp,
    gameState?.game_over,
    gameState?.game_mode,
    aiThinking,
    gameId,
    setGameState,
    setAIThinking,
    clearPendingTiles,
    setExchangeMode,
    showToast,
  ]);

  const handleProfilePasswordChange = useCallback(async ({
    currentPassword,
    newPassword,
  }: {
    currentPassword: string;
    newPassword: string;
  }) => {
    if (!token) {
      return { ok: false, error: "Session expired." };
    }

    try {
      const result = await api.changePassword(token, {
        current_password: currentPassword,
        new_password: newPassword,
      });
      if (!result.ok) {
        return result;
      }
      showToast({
        id: `password-${Date.now()}`,
        type: "success",
        message: "Password updated.",
      });
      return { ok: true };
    } catch (err) {
      return {
        ok: false,
        error: err instanceof Error ? err.message : "Unable to update password.",
      };
    }
  }, [showToast, token]);

  const handleLogout = useCallback(() => {
    setLoggingOut(true);
    setProfileModalOpen(false);
    setGamesModalOpen(false);
    setPromptsModalOpen(false);
    setPromptPreview(null);
    multiplayerSocketRef.current?.close();
    resetGameUi();
    setUserProfile(null);
    setStartingRack(null);
    clearAuth();
    router.push("/");
  }, [resetGameUi, router, setStartingRack, clearAuth]);

  const fetchGameHistory = useCallback(async ({
    page = 1,
    filter = gameHistoryFilter,
    sort = gameHistorySort,
  }: {
    page?: number;
    filter?: GameHistoryFilter;
    sort?: GameHistorySort;
  } = {}) => {
    if (!token) {
      setGameHistoryError("Session expired.");
      return;
    }

    setGameHistoryLoading(true);
    setGameHistoryError(null);
    try {
      const result = await api.listGameHistory(token, {
        game_mode: filter,
        sort,
        page,
        page_size: 8,
      });
      setGameHistoryData(result);
    } catch (err) {
      setGameHistoryError(err instanceof Error ? err.message : "Unable to load games.");
    } finally {
      setGameHistoryLoading(false);
    }
  }, [gameHistoryFilter, gameHistorySort, token]);

  const fetchPrompts = useCallback(async () => {
    setPromptsLoading(true);
    try {
      const result = await fetch("/api/prompts", { cache: "no-store" });
      const catalog = (await result.json().catch(() => [])) as unknown;
      setPrompts(Array.isArray(catalog) ? (catalog as AIPrompt[]) : []);
    } catch {
      setPrompts([]);
    } finally {
      setPromptsLoading(false);
    }
  }, []);

  const handleOpenGamesModal = useCallback(() => {
    setGamesModalOpen(true);
    void fetchGameHistory({ page: 1 });
  }, [fetchGameHistory]);

  const handleOpenPromptsModal = useCallback(() => {
    setPromptsModalOpen(true);
    void fetchPrompts();
  }, [fetchPrompts]);

  const handlePromptSelect = useCallback((prompt: AIPrompt) => {
    setSelectedPromptId(prompt.id);
    setPromptsModalOpen(false);
  }, [setSelectedPromptId]);

  const handlePromptPreview = useCallback((prompt: AIPrompt) => {
    setPromptPreview(prompt);
  }, []);

  const handlePromptSelectFromPreview = useCallback((prompt: AIPrompt) => {
    handlePromptSelect(prompt);
    setPromptPreview(null);
  }, [handlePromptSelect]);

  const handleGameHistoryFilterChange = useCallback((nextFilter: GameHistoryFilter) => {
    setGameHistoryFilter(nextFilter);
    void fetchGameHistory({ filter: nextFilter, sort: gameHistorySort, page: 1 });
  }, [fetchGameHistory, gameHistorySort]);

  const handleGameHistorySortChange = useCallback((nextSort: GameHistorySort) => {
    setGameHistorySort(nextSort);
    void fetchGameHistory({ filter: gameHistoryFilter, sort: nextSort, page: 1 });
  }, [fetchGameHistory, gameHistoryFilter]);

  const handleGameHistoryOpen = useCallback((item: GameHistoryItem) => {
    setGamesModalOpen(false);
    if (item.game_id === gameId) return;
    router.push(item.status === "waiting" ? `/waiting/${item.game_id}` : `/game/${item.game_id}`);
  }, [gameId, router]);

  const handleGameHistoryPrev = useCallback(() => {
    if (!gameHistoryData?.has_previous) return;
    void fetchGameHistory({ page: gameHistoryData.page - 1 });
  }, [fetchGameHistory, gameHistoryData]);

  const handleGameHistoryNext = useCallback(() => {
    if (!gameHistoryData?.has_next) return;
    void fetchGameHistory({ page: gameHistoryData.page + 1 });
  }, [fetchGameHistory, gameHistoryData]);

  const syncState = useCallback(
    async (state?: GameState) => {
      if (state) {
        setGameState(state);
        return state;
      }
      await fetchState();
      return useGameStore.getState().gameState;
    },
    [fetchState, setGameState],
  );

  const mySlotNumber = gameState?.my_slot ?? 0;
  const aiSlotNumber = gameState?.slots.find((slot) => slot.is_ai)?.slot ?? null;
  const opponentSlotInfo = gameState?.slots.find((slot) => slot.slot !== mySlotNumber) ?? null;
  const isMultiplayerGame = gameState?.game_mode === "vs_human";

  const triggerAIMove = useCallback(async () => {
    if (!token || !gameState || gameState.game_over) return;
    if (gameState.game_mode !== "vs_ai" || aiSlotNumber == null) return;
    if (gameState.current_turn_slot !== aiSlotNumber) return;
    if (aiInFlightRef.current) return;

    const preferenceModelId = selectedModelId || gameState.ai_model_id || "";
    const turnStartedAtMs = Date.now();
    const turnAnchor = {
      gameId,
      moveCount: gameState.move_count,
      aiSlot: aiSlotNumber,
    };

    aiInFlightRef.current = true;
    clearAICandidates();
    clearAIFallbackProgress();
    setAIThinking(true);
    setAIStatusMessage(`Exploring legal words with ${preferenceModelId}...`);
    setAiError(null);
    setAIBlockerModal(null);
    startCountdown(aiTimeout);

    try {
      let queue;
      try {
        const catalog = await api.getModels();
        queue = buildFallbackQueue(
          preferenceModelId,
          catalog.map((row) => ({
            provider: row.provider,
            model_id: row.model_id,
          })),
        );
      } catch {
        queue = fallbackQueueForCatalogFailure(preferenceModelId);
      }
      setAIFallbackAttempts(
        queue.map((pair) => ({
          provider: pair.provider,
          modelId: pair.model_id,
          status: "pending" as const,
        })),
      );

      const result = await orchestrateFallbackTurn({
        queue,
        turnStartedAtMs,
        aiTimeoutSeconds: aiTimeout,
        maxStepsTotal: aiMaxSteps,
        now: Date.now,
        anchor: turnAnchor,
        fetchGameState: async () => {
          try {
            const state = (await api.getGameState(token, gameId)) as GameState;
            setGameState(state);
            return {
              game_id: state.game_id,
              move_count: state.move_count,
              status: state.status,
              current_turn_slot: state.current_turn_slot,
              game_over: state.game_over,
            };
          } catch {
            return null;
          }
        },
        runStream: async ({ pair, attemptIndex, timeoutSeconds, maxStepsRemaining }) => {
          const attemptLabel = `Attempt ${attemptIndex + 1}/${queue.length} · ${providerBadgeLabel(pair.provider)} · ${pair.model_id}`;
          setAIStatusMessage(attemptLabel);
          setAIFallbackActiveIndex(attemptIndex);
          const payload = aiMoveRequestBody({
            gameId,
            token,
            preferenceModelId,
            runtimeModelId: pair.model_id,
            timeout: timeoutSeconds,
            maxSteps: maxStepsRemaining,
          });
          const res = await fetch("/api/ai/move", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              game_id: payload.game_id,
              token: payload.token,
              model_id: payload.model_id,
              runtime_model_id: payload.runtime_model_id,
              timeout: payload.timeout,
              max_steps: payload.max_steps,
            }),
          });
          const contentType = res.headers.get("content-type") ?? "";
          if (!res.ok || !contentType.includes("text/event-stream")) {
            throw new Error(await getStreamStartError(res));
          }
          return consumeAIStream(res, {
            onCandidate: (candidate) => {
              addAICandidate(candidate);
            },
            onDone: (data) => {
              const move = data as unknown as MoveResult;
              setLastMoveResult(move);
              if (move.state) {
                setGameState(move.state);
              }
              const telemetry = readAiTurnTelemetry(data);
              if (telemetry) patchAITurnTelemetry(telemetry);
            },
            onStatus: (msg) => {
              setAIStatusMessage(`${attemptLabel} — ${msg}`);
            },
            onTelemetry: (telemetry) => {
              patchAITurnTelemetry(telemetry);
            },
          }).then((terminal) => {
            if (terminal.kind === "coded_provider_error") {
              markAIFallbackFailed(attemptIndex);
            }
            return terminal;
          });
        },
      });

      const last = result.lastTerminal;
      const doneData = last?.kind === "done" ? last.data : null;

      if (doneData) {
        const action = doneData.action as string;
        if (action === "pass") {
          showToast({
            id: `pass-${Date.now()}`,
            type: "ai_pass",
            message: "AI passes",
          });
        } else if (action === "place") {
          const bestWord = doneData.best_word as string | undefined;
          const bestScore = doneData.best_score as number | undefined;
          const words = doneData.words as Array<{ word: string }> | undefined;
          showToast({
            id: `played-${Date.now()}`,
            type: "ai_played",
            message: `AI played ${bestWord ?? "a word"}`,
            words: words?.map((w) => w.word) ?? (bestWord ? [bestWord] : []),
            score: bestScore ?? (doneData.points as number | undefined) ?? 0,
          });
        } else if (action === "exchange") {
          showToast({
            id: `exchange-${Date.now()}`,
            type: "ai_pass",
            message: "AI exchanged tiles",
          });
        }
      } else if (
        result.stopReason === "queue_exhausted"
        || result.stopReason === "deadline"
        || result.stopReason === "empty_queue"
        || result.stopReason === "budget_exhausted"
      ) {
        patchAITurnTelemetry({ humanState: "providers exhausted" });
        setAiApproved(false);
        if (last?.kind === "coded_provider_error") {
          const blocker = normalizeAIBlocker(last.message, last.code);
          if (blocker) {
            setAiError(blocker.message);
            setAIBlockerModal(blocker);
          } else {
            setAiError(last.message);
          }
        } else if (result.stopReason === "empty_queue") {
          const blocker = normalizeAIBlocker("", "provider_unavailable");
          setAiError(blocker?.message ?? "No eligible free rival is available.");
          setAIBlockerModal(blocker);
        } else if (result.stopReason === "deadline") {
          const blocker = normalizeAIBlocker("", "provider_unavailable");
          setAiError(blocker?.message ?? "AI thinking time ran out.");
          setAIBlockerModal(blocker);
        }
      } else if (result.stopReason === "generic_error" || result.stopReason === "no_terminal") {
        setAiApproved(false);
        const message = last?.kind === "generic_error" ? last.message : "AI move failed";
        console.error("AI move failed:", message);
        setAiError(message);
      }

      const latest = await syncState((doneData as unknown as MoveResult | null)?.state);
      if (latest?.game_over && latest.winner_slot === latest.my_slot) {
        confetti({ particleCount: 200, spread: 100, origin: { y: 0.6 } });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "AI move failed";
      setAiApproved(false);
      console.error("AI move failed:", err);
      setAiError(message);
    } finally {
      setAIThinking(false);
      setAIStatusMessage(null);
      clearAIFallbackProgress();
      stopCountdown();
      aiInFlightRef.current = false;
    }
  }, [
    token, gameState, gameId, selectedModelId, aiTimeout, aiMaxSteps, aiSlotNumber,
    setAIThinking, setLastMoveResult, setGameState, setAIStatusMessage, syncState,
    clearAICandidates, addAICandidate, startCountdown, stopCountdown, showToast,
    setAIFallbackAttempts, setAIFallbackActiveIndex, markAIFallbackFailed,
    clearAIFallbackProgress, patchAITurnTelemetry,
  ]);

  useEffect(() => {
    if (
      aiApproved &&
      gameState &&
      gameState.game_mode === "vs_ai" &&
      gameState.current_turn_slot === aiSlotNumber &&
      !gameState.game_over &&
      !aiThinking &&
      !aiInFlightRef.current
    ) {
      const timeout = setTimeout(triggerAIMove, 500);
      return () => clearTimeout(timeout);
    }
  }, [aiApproved, aiSlotNumber, gameState, aiThinking, triggerAIMove]);

  useEffect(() => {
    const authToken = token;
    if (!authToken || !isMultiplayerGame) return;
    const tokenValue: string = authToken;

    let active = true;

    async function connectRealtime() {
      try {
        const ticketResult = (await api.getWSTicket(tokenValue, gameId)) as WSTicketResponse;
        if (!active) return;

        const socket = new WebSocket(buildGameWebSocketUrl(gameId, ticketResult.ticket));
        multiplayerSocketRef.current = socket;

        socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data) as {
              type?: string;
              state?: GameState;
              message?: GameState["chat_messages"][number];
              error?: string;
            };

            if (data.state) {
              setGameState(data.state);
              if (data.state.game_over && data.state.winner_slot === data.state.my_slot) {
                confetti({ particleCount: 200, spread: 100, origin: { y: 0.6 } });
              }
              return;
            }

            if (data.type === "chat_message" && data.message) {
              const latest = useGameStore.getState().gameState;
              if (!latest) return;
              setGameState({
                ...latest,
                chat_messages: [...latest.chat_messages, data.message],
              });
              return;
            }

            if (data.type === "error" && data.error) {
              showToast({
                id: `ws-${Date.now()}`,
                type: "error",
                message: data.error,
              });
            }
          } catch {
            showToast({
              id: `ws-${Date.now()}`,
              type: "error",
              message: "Realtime sync failed",
            });
          }
        };

        socket.onerror = () => {
          showToast({
            id: `ws-${Date.now()}`,
            type: "error",
            message: "Realtime connection failed",
          });
        };
      } catch (err) {
        showToast({
          id: `ws-${Date.now()}`,
          type: "error",
          message: err instanceof Error ? err.message : "Realtime connection failed",
        });
      }
    }

    void connectRealtime();

    return () => {
      active = false;
      multiplayerSocketRef.current?.close();
      multiplayerSocketRef.current = null;
    };
  }, [gameId, isMultiplayerGame, setGameState, showToast, token]);

  const clearDragState = useCallback(() => {
    setActiveDragTile(null);
    setDragPreviewTarget(null);
  }, []);

  const getValidPreviewTarget = useCallback((row: number, col: number) => {
    const boardLetter = gameState?.board?.[row]?.[col];
    if (boardLetter && boardLetter !== ".") return null;
    if (pendingTiles.some((t) => t.row === row && t.col === col)) return null;
    return { row, col };
  }, [gameState, pendingTiles]);

  const placeRackTileAt = useCallback((tile: RackDragData, row: number, col: number) => {
    const target = getValidPreviewTarget(row, col);
    if (!target) return false;

    if (tile.letter === "?") {
      openBlankPicker(target.row, target.col, tile.index);
    } else {
      addPendingTile({
        row: target.row,
        col: target.col,
        letter: tile.letter,
        blank_as: null,
        rackIndex: tile.index,
      });
    }

    return true;
  }, [addPendingTile, getValidPreviewTarget, openBlankPicker]);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const activeData = event.active.data.current as RackDragData | undefined;
    if (!activeData || activeData.origin !== "rack") {
      clearDragState();
      return;
    }

    setSelectedRackTile(null);
    setActiveDragTile(activeData);
  }, [clearDragState]);

  const handleDragOver = useCallback((event: DragOverEvent) => {
    if (!activeDragTile) return;

    const overData = event.over?.data.current as { row: number; col: number } | undefined;
    if (!overData) {
      setDragPreviewTarget(null);
      return;
    }

    setDragPreviewTarget(getValidPreviewTarget(overData.row, overData.col));
  }, [activeDragTile, getValidPreviewTarget]);

  const handleDragCancel = useCallback(() => {
    window.requestAnimationFrame(() => {
      clearDragState();
    });
  }, [clearDragState]);

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    const activeData = active.data.current as RackDragData | undefined;
    if (over) {
      const overData = over.data.current as { row: number; col: number } | undefined;
      if (overData && activeData && activeData.origin === "rack") {
        placeRackTileAt(activeData, overData.row, overData.col);
      }
    }

    window.requestAnimationFrame(() => {
      clearDragState();
    });
  }, [clearDragState, placeRackTileAt]);

  const handleBlankSelect = (letter: string) => {
    const target = useGameStore.getState().blankPickerTarget;
    if (!target) return;
    addPendingTile({ row: target.row, col: target.col, letter: "?", blank_as: letter, rackIndex: target.rackIndex });
  };

  const handlePlay = async () => {
    if (!token || pendingTiles.length === 0) return;
    const placements = pendingTiles.map((t) => ({
      row: t.row, col: t.col, letter: t.letter, blank_as: t.blank_as ?? undefined,
    }));

    try {
      const validation = (await api.validateMove(token, gameId, placements)) as MoveValidationResult;
      if (!validation.valid) {
        const invalidWords = (validation.words ?? [])
          .filter((word) => !word.valid)
          .map((word) => word.word);

        if (invalidWords.length > 0) {
          showToast({
            id: `invalid-${Date.now()}`,
            type: "invalid_word",
            message: validation.reason ?? "Invalid words",
            words: invalidWords,
          });
          return;
        }

        showToast({
          id: `err-${Date.now()}`,
          type: "placement_error",
          message: validation.reason ?? "Move rejected",
        });
        return;
      }

      const result = (await api.submitMove(token, gameId, placements)) as MoveResult;
      setLastMoveResult(result);
      if (result.ok) {
        clearPendingTiles();
        setAiApproved(gameState?.game_mode === "vs_ai");
        const latest = await syncState(result.state);
        if (latest?.game_over && latest.winner_slot === latest.my_slot) {
          confetti({ particleCount: 200, spread: 100, origin: { y: 0.6 } });
        }
        return;
      }

      if (result.invalid_words && result.invalid_words.length > 0) {
        showToast({
          id: `invalid-${Date.now()}`,
          type: "invalid_word",
          message: result.error ?? "Invalid words",
          words: result.invalid_words,
        });
        return;
      }

      showToast({
        id: `err-${Date.now()}`,
        type: "placement_error",
        message: result.error ?? "Move rejected",
      });
    } catch (err) {
      showToast({
        id: `err-${Date.now()}`,
        type: "placement_error",
        message: err instanceof Error ? err.message : "Move rejected",
      });
    }
  };

  const handleExchange = async () => {
    if (!token) return;
    const rack = gameState?.my_rack ?? [];
    const letters = Array.from(exchangeSelected).map((i) => rack[i]);
    try {
      const result = (await api.exchange(token, gameId, letters)) as MoveResult;
      if (result.ok) {
        setExchangeMode(false);
        setAiApproved(gameState?.game_mode === "vs_ai");
        await syncState(result.state);
        return;
      }
      showToast({
        id: `exchange-${Date.now()}`,
        type: "placement_error",
        message: result.error ?? "Exchange rejected",
      });
    } catch (err) {
      showToast({
        id: `exchange-${Date.now()}`,
        type: "placement_error",
        message: err instanceof Error ? err.message : "Exchange rejected",
      });
    }
  };

  const handlePass = async () => {
    if (!token) return;
    try {
      const result = (await api.pass(token, gameId)) as MoveResult;
      if (result.ok) {
        setAiApproved(gameState?.game_mode === "vs_ai");
        await syncState(result.state);
        return;
      }
      showToast({
        id: `pass-${Date.now()}`,
        type: "placement_error",
        message: result.error ?? "Pass rejected",
      });
    } catch (err) {
      showToast({
        id: `pass-${Date.now()}`,
        type: "placement_error",
        message: err instanceof Error ? err.message : "Pass rejected",
      });
    }
  };

  const handleSendChat = useCallback((body: string) => {
    const socket = multiplayerSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      showToast({
        id: `chat-${Date.now()}`,
        type: "error",
        message: "Chat is offline",
      });
      return;
    }
    socket.send(JSON.stringify({ type: "chat_message", body }));
  }, [showToast]);

  const isMyTurn = gameState?.current_turn_slot === gameState?.my_slot;
  const isAITurn =
    gameState?.game_mode === "vs_ai" &&
    aiSlotNumber != null &&
    gameState?.current_turn_slot === aiSlotNumber &&
    !gameState?.game_over;
  const showAIPrompt = isAITurn && !aiApproved && !aiThinking;
  const rackCanPlace = isMyTurn && !gameState?.game_over && !aiThinking;
  const boardDragPreview = activeDragTile && dragPreviewTarget
    ? {
        ...dragPreviewTarget,
      }
    : null;
  const turnStatus = useMemo(() => {
    if (!gameState || gameState.game_over) {
      return { text: null, tone: "neutral" as const };
    }
    if (exchangeMode && isMyTurn) {
      return { text: "Select tiles to exchange", tone: "active" as const };
    }
    if (showAIPrompt) {
      return { text: "AI move ready", tone: "active" as const };
    }
    if (aiThinking) {
      return {
        text: gameState.game_mode === "vs_ai" ? "AI is thinking" : "Opponent is playing",
        tone: "waiting" as const,
      };
    }
    if (isMyTurn) {
      return { text: "Your turn", tone: "active" as const };
    }
    if (gameState.game_mode === "vs_human") {
      return {
        text: `${opponentSlotInfo?.username ?? "Opponent"} is playing`,
        tone: "waiting" as const,
      };
    }
    return { text: "Waiting for the AI", tone: "waiting" as const };
  }, [aiThinking, exchangeMode, gameState, isMyTurn, opponentSlotInfo?.username, showAIPrompt]);
  const frameBorderColor = THEME_FRAME_BORDER[boardTheme];
  const activeHeaderModelName = useMemo(() => {
    if (gameState?.game_mode === "vs_human") {
      return opponentSlotInfo?.username ?? "Opponent";
    }
    if (selectedModelId && gameState?.ai_model_id !== selectedModelId) {
      return humanizeModelId(selectedModelId) ?? gameState?.ai_model_display_name ?? "Choose rival";
    }
    return gameState?.ai_model_display_name ?? humanizeModelId(gameState?.ai_model_id) ?? "Choose rival";
  }, [gameState?.ai_model_display_name, gameState?.ai_model_id, gameState?.game_mode, opponentSlotInfo?.username, selectedModelId]);
  const effectivePromptId = selectedPromptId ?? gameState?.ai_prompt_id ?? null;
  const activePromptLabel = useMemo(() => {
    if (gameState?.game_mode !== "vs_ai") return null;
    if (effectivePromptId != null) {
      const selectedPrompt = prompts.find((prompt) => prompt.id === effectivePromptId);
      if (selectedPrompt) return selectedPrompt.name;
    }
    return gameState?.ai_prompt_name ?? "Initial";
  }, [effectivePromptId, gameState?.ai_prompt_name, gameState?.game_mode, prompts]);
  const rackTileSize = isCoarsePointer ? "rack" : "lg";

  const handleRackTileSelect = useCallback((tile: { letter: string; index: number }) => {
    if (!rackCanPlace || exchangeMode) return;
    setSelectedRackTile((current) =>
      current?.index === tile.index
        ? null
        : { ...tile, origin: "rack" },
    );
  }, [exchangeMode, rackCanPlace]);

  const handleBoardTilePlacement = useCallback((row: number, col: number) => {
    if (!selectedRackTile || !rackCanPlace) return;
    if (placeRackTileAt(selectedRackTile, row, col)) {
      setSelectedRackTile(null);
    }
  }, [placeRackTileAt, rackCanPlace, selectedRackTile]);

  useEffect(() => {
    if (!selectedRackTile) return;
    if (!rackCanPlace || exchangeMode) {
      setSelectedRackTile(null);
      return;
    }

    const rack = isPlausibleRack(gameState?.my_rack, gameState?.alphabet)
      ? gameState.my_rack
      : isPlausibleRack(startingRack, gameState?.alphabet)
        ? startingRack
        : [];
    const tileStillAvailable =
      rack[selectedRackTile.index] === selectedRackTile.letter &&
      !pendingTiles.some((tile) => tile.rackIndex === selectedRackTile.index);

    if (!tileStillAvailable) {
      setSelectedRackTile(null);
    }
  }, [exchangeMode, gameState?.alphabet, gameState?.my_rack, pendingTiles, rackCanPlace, selectedRackTile, startingRack]);

  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-stone-950 via-stone-900 to-stone-950 flex items-center justify-center">
        <div className="text-center">
          <p className="text-stone-400 mb-4">Session expired</p>
          <button onClick={() => router.push("/")}
            className="px-6 py-3 rounded-xl bg-amber-500 text-stone-900 font-semibold">
            Sign In
          </button>
        </div>
      </div>
    );
  }

  return (
    <DndContext
      sensors={isCoarsePointer ? [] : sensors}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragCancel={handleDragCancel}
      onDragEnd={handleDragEnd}
    >
      <AnimatePresence>
        {newGameTransitioning && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            className="fixed inset-0 z-[90] bg-black"
          />
        )}
      </AnimatePresence>

      <div className="min-h-screen bg-gradient-to-br from-stone-950 via-stone-900 to-stone-950 text-stone-100">
        <div className="mx-auto flex max-w-[960px] flex-col gap-2 px-4 py-3 sm:px-5 sm:py-4">
          <ScorePanel
            opponentLabel={activeHeaderModelName}
            showRivalPicker={gameState?.game_mode === "vs_ai"}
            showPromptPicker={gameState?.game_mode === "vs_ai"}
            promptLabel={activePromptLabel}
            frameBorderColor={frameBorderColor}
            onBack={() => router.push("/play")}
            onOpenRivalPicker={() => router.push("/settings?focus=rival")}
            onOpenPromptPicker={handleOpenPromptsModal}
            onNewGame={() => void handleNewGame()}
            onGiveUp={() => void handleGiveUp()}
            onOpenGames={handleOpenGamesModal}
            onOpenSettings={() => router.push("/settings")}
            onOpenProfile={() => setProfileModalOpen(true)}
            onLogout={handleLogout}
            startingNewGame={startingNewGame}
            givingUp={givingUp}
            disableGiveUp={givingUp || gameState?.game_over || aiThinking}
            loggingOut={loggingOut}
          />
          <LayoutGroup id={`game-${gameId}-rack-board`}>
            <div className="mt-5">
              <Board
                dragPreview={boardDragPreview}
                isDraggingTile={!!activeDragTile}
                onPlaceTile={handleBoardTilePlacement}
              />
            </div>
            <div
              className={`relative rounded-[1.55rem] border border-white/8 bg-black px-4 py-1.75 shadow-[0_22px_52px_rgba(0,0,0,0.28)] ${premiumLookEnabled ? "overflow-hidden backdrop-blur-[14px]" : ""}`}
              style={
                premiumLookEnabled
                  ? { borderColor: frameBorderColor, ...PREMIUM_FOOTER_STYLE }
                  : { borderColor: frameBorderColor }
              }
              onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
            >
              {premiumLookEnabled ? (
                <>
                  <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/54 to-transparent" />
                  <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,214,120,0.08),transparent_40%)] opacity-80" />
                </>
              ) : null}
              {isMyTurn ? (
                <div className="flex flex-col gap-2 lg:grid lg:grid-cols-[auto_minmax(0,1fr)_auto] lg:grid-rows-[auto_auto_auto] lg:items-center lg:gap-x-2.5 lg:gap-y-1.75">
                  <div className="order-1 w-full lg:col-start-2 lg:row-start-1 lg:min-w-[430px] lg:w-auto">
                    <TileRack
                      canPlaceByTap={rackCanPlace}
                      dragEnabled={!isCoarsePointer}
                      tileSize={rackTileSize}
                      selectedRackTileIndex={selectedRackTile?.index ?? null}
                      onRackTileSelect={handleRackTileSelect}
                    />
                  </div>
                  <GameControls
                    onPlay={handlePlay}
                    onExchange={handleExchange}
                    onPass={handlePass}
                    disabled={!isMyTurn || gameState?.game_over}
                  />
                </div>
              ) : (
                <div className="relative flex flex-col gap-2">
                  <div className="mx-auto w-full max-w-fit opacity-55 saturate-75">
                    <TileRack dragEnabled={!isCoarsePointer} tileSize={rackTileSize} />
                  </div>
                  {showAIPrompt ? (
                    <>
                      <div className="flex justify-center lg:absolute lg:right-0 lg:top-1/2 lg:mt-0 lg:-translate-y-1/2">
                        <div className="rounded-full bg-transparent p-0 shadow-[0_22px_44px_rgba(0,0,0,0.38),0_0_30px_rgba(22,163,74,0.24)] transition-all duration-200 hover:shadow-[0_24px_48px_rgba(0,0,0,0.42),0_0_34px_rgba(34,197,94,0.28)]">
                          <button
                            onClick={() => setAiApproved(true)}
                            className="group inline-flex min-w-[5.2rem] items-center justify-center rounded-full border border-emerald-200/28 bg-[linear-gradient(135deg,rgba(34,197,94,1),rgba(22,163,74,1)_42%,rgba(11,107,53,1))] px-4 py-2.5 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.16),0_16px_32px_rgba(0,0,0,0.38),0_0_24px_rgba(22,163,74,0.24)] transition-all duration-200 active:scale-[0.97] hover:border-emerald-50/36 hover:bg-[linear-gradient(135deg,rgba(46,214,108,1),rgba(26,179,83,1)_42%,rgba(14,122,61,1))] hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.2),0_18px_36px_rgba(0,0,0,0.42),0_0_30px_rgba(34,197,94,0.3)]"
                          >
                            <span className="text-[1.12rem] font-black leading-none tracking-[0.01em] text-white [text-shadow:0_2px_0_rgba(0,0,0,0.55)] sm:text-[1.34rem]">
                              Play
                            </span>
                          </button>
                        </div>
                      </div>
                      {aiError && (
                        <motion.div
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -8 }}
                          className="mt-4 text-center text-xs text-red-400/80 lg:pr-[184px]"
                        >
                          Last error: {aiError}
                        </motion.div>
                      )}
                    </>
                  ) : null}
                </div>
              )}
            </div>
            {turnStatus.text ? (
              <section className="flex justify-center pt-2" aria-live="polite">
                <TurnStatusNotice text={turnStatus.text} tone={turnStatus.tone} />
              </section>
            ) : null}
          </LayoutGroup>

          {isMultiplayerGame && (
            <ChatPanel
              messages={gameState?.chat_messages ?? []}
              disabled={gameState?.status !== "active"}
              onSend={handleSendChat}
            />
          )}

          {/* Game over */}
          <AnimatePresence>
            {gameState?.game_over && (
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                className="text-center p-6 bg-stone-800/80 backdrop-blur rounded-xl">
                <h2 className="text-3xl font-bold mb-2">
                  {gameState.winner_slot === gameState.my_slot ? "Victory!" : gameState.winner_slot == null ? "Draw!" : "Game Over"}
                </h2>
                <p className="text-stone-400 mb-4">
                  {gameState.slots.map((s) => `${s.username ?? "Waiting"}: ${s.score}`).join(" vs ")}
                </p>
                <button onClick={() => void handleNewGame()}
                  className="px-6 py-3 rounded-xl bg-amber-500 text-stone-900 font-semibold hover:bg-amber-400 transition-colors">
                  {startingNewGame ? "Starting..." : "New Game"}
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {gameState?.game_mode === "vs_ai" && <AIThinkingOverlay />}
      <BlankPicker onSelect={handleBlankSelect} />
      <DragOverlay
        adjustScale={false}
        dropAnimation={{
          ...defaultDropAnimation,
          duration: 150,
          easing: "cubic-bezier(0.22, 1, 0.36, 1)",
          sideEffects: defaultDropAnimationSideEffects({
            styles: {
              active: {
                opacity: "0.22",
              },
            },
          }),
        }}
      >
        {activeDragTile ? (
          <div className="pointer-events-none -translate-y-2">
            <Tile
              letter={activeDragTile.letter}
              isBlank={activeDragTile.letter === "?"}
              isDragging
              size="lg"
            />
          </div>
        ) : null}
      </DragOverlay>

      <AnimatePresence>
        {gamesModalOpen && (
          <GameHistoryModal
            data={gameHistoryData}
            filter={gameHistoryFilter}
            sort={gameHistorySort}
            loading={gameHistoryLoading}
            error={gameHistoryError}
            activeGameId={gameId}
            onClose={() => setGamesModalOpen(false)}
            onFilterChange={handleGameHistoryFilterChange}
            onPrevPage={handleGameHistoryPrev}
            onNextPage={handleGameHistoryNext}
            onRefresh={() => void fetchGameHistory({ page: gameHistoryData?.page ?? 1 })}
            onSortChange={handleGameHistorySortChange}
            onOpenGame={handleGameHistoryOpen}
          />
        )}
        {profileModalOpen && (
          <ProfileModal
            profile={userProfile}
            onClose={() => setProfileModalOpen(false)}
            onLogout={handleLogout}
            onOpenSettings={() => {
              setProfileModalOpen(false);
              router.push("/settings");
            }}
            onChangePassword={handleProfilePasswordChange}
            loggingOut={loggingOut}
          />
        )}
        {promptsModalOpen && (
          <PromptCatalogModal
            prompts={prompts}
            selectedPromptId={effectivePromptId}
            loading={promptsLoading}
            savingPromptId={savingPromptId}
            onClose={() => setPromptsModalOpen(false)}
            onSelect={handlePromptSelect}
            onPreview={handlePromptPreview}
          />
        )}
        {promptPreview && (
          <PromptPreviewModal
            prompt={promptPreview}
            selected={effectivePromptId === promptPreview.id}
            saving={savingPromptId === promptPreview.id}
            onSelect={handlePromptSelectFromPreview}
            onClose={() => setPromptPreview(null)}
          />
        )}
        {aiBlockerModal && (
          <AIBlockerOverlay
            modal={aiBlockerModal}
            onClose={() => setAIBlockerModal(null)}
            onOpenSettings={() => {
              setAIBlockerModal(null);
              router.push("/settings");
            }}
          />
        )}
        {toast && (
          <ToastOverlay
            key={toast.id}
            toast={toast}
            onDone={() => setToast(null)}
          />
        )}
      </AnimatePresence>
    </DndContext>
  );
}
