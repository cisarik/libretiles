"use client";

import { useEffect, useCallback, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import confetti from "canvas-confetti";
import { motion, AnimatePresence } from "framer-motion";

import { Board } from "@/components/board/Board";
import { TileRack } from "@/components/tiles/TileRack";
import { ScorePanel } from "@/components/game/ScorePanel";
import { GameControls } from "@/components/game/GameControls";
import { BlankPicker } from "@/components/game/BlankPicker";
import { AIThinkingOverlay } from "@/components/game/AIThinkingOverlay";
import { useGameStore } from "@/hooks/useGameStore";
import { api } from "@/lib/api";
import type { GameState, MoveResult, AICandidate } from "@/lib/types";

async function consumeAIStream(
  response: Response,
  callbacks: {
    onCandidate: (c: AICandidate) => void;
    onDone: (data: Record<string, unknown>) => void;
    onError: (msg: string) => void;
    onStatus: (msg: string) => void;
  },
) {
  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError("No response stream");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      try {
        const json = JSON.parse(trimmed.slice(6));
        const type = json.type as string;
        if (type === "candidate") {
          callbacks.onCandidate({
            word: json.word ?? "???",
            score: json.score ?? 0,
            valid: json.valid ?? false,
            isBest: json.isBest ?? false,
            timestamp: json.timestamp ?? 0,
            allWords: json.allWords,
          });
        } else if (type === "thinking") {
          if (typeof json.message === "string" && json.message.length > 0) {
            callbacks.onStatus(json.message);
          } else if (typeof json.model === "string") {
            callbacks.onStatus(`Thinking with ${json.model}`);
          }
        } else if (type === "tool_use") {
          callbacks.onStatus(
            json.tool === "validateMove"
              ? `Testing ${json.tileCount ?? "new"} tile move...`
              : "Checking candidate words against the dictionary...",
          );
        } else if (type === "tool_result") {
          if (json.tool === "validateMove") {
            callbacks.onStatus(
              json.valid
                ? `Valid move found for ${json.score ?? 0} points.`
                : "Rejected. Trying another line...",
            );
          }
        } else if (type === "done") {
          callbacks.onDone(json);
        } else if (type === "error") {
          callbacks.onError(json.error ?? "AI error");
        }
      } catch { /* malformed line */ }
    }
  }
}

// ---------- Toast types ----------
type Toast = {
  id: string;
  type: "invalid_word" | "placement_error" | "ai_pass" | "ai_played" | "error";
  message: string;
  words?: string[];
  score?: number;
};

function ToastOverlay({ toast, onDone }: { toast: Toast; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, toast.type === "ai_pass" ? 3500 : 3000);
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
          <p className="text-red-400/60 text-xs mt-3">Not in Collins Scrabble Words 2019</p>
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
            className="text-sky-300 font-bold text-lg mb-1"
          >
            AI Passes
          </motion.div>
          <p className="text-sky-400/60 text-sm">
            Couldn&apos;t find a valid move — your turn!
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
          p-5 shadow-2xl shadow-emerald-500/15 max-w-sm text-center pointer-events-auto">
          <motion.div
            animate={{ scale: [1, 1.2, 1] }}
            transition={{ duration: 0.5 }}
            className="text-4xl mb-2"
          >
            <svg className="w-12 h-12 mx-auto text-emerald-400" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          </motion.div>
          <div className="text-emerald-300 font-bold text-base">
            AI played for <span className="text-emerald-200 text-xl font-black">{toast.score}</span> pts
          </div>
          {toast.words && toast.words.length > 0 && (
            <div className="flex flex-wrap gap-1 justify-center mt-2">
              {toast.words.map((w) => (
                <span key={w} className="px-2 py-0.5 bg-emerald-500/15 border border-emerald-400/20
                  rounded-md font-mono font-bold text-emerald-200 text-sm tracking-wider">
                  {w}
                </span>
              ))}
            </div>
          )}
        </div>
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

export default function GamePage() {
  const params = useParams();
  const router = useRouter();
  const gameId = params.id as string;

  const token = useGameStore((s) => s.token);
  const gameState = useGameStore((s) => s.gameState);
  const setGameState = useGameStore((s) => s.setGameState);
  const pendingTiles = useGameStore((s) => s.pendingTiles);
  const addPendingTile = useGameStore((s) => s.addPendingTile);
  const clearPendingTiles = useGameStore((s) => s.clearPendingTiles);
  const setExchangeMode = useGameStore((s) => s.setExchangeMode);
  const exchangeSelected = useGameStore((s) => s.exchangeSelected);
  const setLastMoveResult = useGameStore((s) => s.setLastMoveResult);
  const setAIThinking = useGameStore((s) => s.setAIThinking);
  const aiThinking = useGameStore((s) => s.aiThinking);
  const openBlankPicker = useGameStore((s) => s.openBlankPicker);
  const selectedModelId = useGameStore((s) => s.selectedModelId);
  const aiTimeout = useGameStore((s) => s.aiTimeout);
  const addAICandidate = useGameStore((s) => s.addAICandidate);
  const clearAICandidates = useGameStore((s) => s.clearAICandidates);
  const setAICountdown = useGameStore((s) => s.setAICountdown);
  const setAIStatusMessage = useGameStore((s) => s.setAIStatusMessage);

  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const aiInFlightRef = useRef(false);

  const [aiApproved, setAiApproved] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 150, tolerance: 5 },
    }),
  );

  const fetchState = useCallback(async () => {
    if (!token) return;
    const state = (await api.getGameState(token, gameId, 0)) as GameState;
    setGameState(state);
  }, [token, gameId, setGameState]);

  useEffect(() => { fetchState(); }, [fetchState]);

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

  const triggerAIMove = useCallback(async () => {
    if (!token || !gameState || gameState.game_over) return;
    if (gameState.current_turn_slot !== 1) return;
    if (aiInFlightRef.current) return;

    aiInFlightRef.current = true;
    clearAICandidates();
    setAIThinking(true);
    setAIStatusMessage("Exploring legal words and validating the board...");
    setAiError(null);
    startCountdown(aiTimeout);

    try {
      const res = await fetch("/api/ai/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          game_id: gameId,
          token,
          model_id: selectedModelId,
          timeout: aiTimeout,
        }),
      });

      let doneData: Record<string, unknown> | null = null;

      await consumeAIStream(res, {
        onCandidate: (candidate) => {
          addAICandidate(candidate);
        },
        onDone: (data) => {
          doneData = data;
          const result = data as unknown as MoveResult;
          setLastMoveResult(result);
          if (result.state) {
            setGameState(result.state);
          }
        },
        onError: (msg) => {
          console.error("AI stream error:", msg);
          setAiError(msg);
        },
        onStatus: (msg) => {
          setAIStatusMessage(msg);
        },
      });

      setAIThinking(false);
      setAIStatusMessage(null);
      stopCountdown();

      if (doneData) {
        const action = (doneData as Record<string, unknown>).action as string;
        if (action === "pass") {
          showToast({
            id: `pass-${Date.now()}`,
            type: "ai_pass",
            message: "AI couldn't find a valid move",
          });
        } else if (action === "place") {
          const bestWord = (doneData as Record<string, unknown>).best_word as string | undefined;
          const bestScore = (doneData as Record<string, unknown>).best_score as number | undefined;
          const words = (doneData as Record<string, unknown>).words as Array<{ word: string }> | undefined;
          showToast({
            id: `played-${Date.now()}`,
            type: "ai_played",
            message: `AI played ${bestWord ?? "a word"}`,
            words: words?.map((w) => w.word) ?? (bestWord ? [bestWord] : []),
            score: bestScore ?? (doneData as Record<string, unknown>).points as number | undefined ?? 0,
          });
        }
      }

      const latest = await syncState((doneData as MoveResult | null)?.state);
      if (latest?.game_over && latest.winner_slot === 0) {
        confetti({ particleCount: 200, spread: 100, origin: { y: 0.6 } });
      }
    } catch (err) {
      console.error("AI move failed:", err);
      setAiError(err instanceof Error ? err.message : "AI move failed");
      setAIThinking(false);
      setAIStatusMessage(null);
      stopCountdown();
    } finally {
      aiInFlightRef.current = false;
    }
  }, [
    token, gameState, gameId, selectedModelId, aiTimeout,
    setAIThinking, setLastMoveResult, setGameState, setAIStatusMessage, syncState,
    clearAICandidates, addAICandidate, startCountdown, stopCountdown, showToast,
  ]);

  useEffect(() => {
    if (
      aiApproved &&
      gameState &&
      gameState.current_turn_slot === 1 &&
      !gameState.game_over &&
      !aiThinking &&
      !aiInFlightRef.current
    ) {
      const timeout = setTimeout(triggerAIMove, 500);
      return () => clearTimeout(timeout);
    }
  }, [aiApproved, gameState, aiThinking, triggerAIMove]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const overData = over.data.current as { row: number; col: number } | undefined;
    const activeData = active.data.current as { letter: string; index: number; origin: string } | undefined;
    if (!overData || !activeData || activeData.origin !== "rack") return;
    const { row, col } = overData;
    const boardLetter = gameState?.board?.[row]?.[col];
    if (boardLetter && boardLetter !== ".") return;
    if (pendingTiles.some((t) => t.row === row && t.col === col)) return;

    if (activeData.letter === "?") {
      openBlankPicker(row, col, activeData.index);
    } else {
      addPendingTile({ row, col, letter: activeData.letter, blank_as: null, rackIndex: activeData.index });
    }
  };

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
      const result = (await api.submitMove(token, gameId, 0, placements)) as MoveResult;
      setLastMoveResult(result);
      clearPendingTiles();
      if (result.ok) {
        setAiApproved(true);
        const latest = await syncState(result.state);
        if (latest?.game_over && latest.winner_slot === 0) {
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
      clearPendingTiles();
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
      const result = (await api.exchange(token, gameId, 0, letters)) as MoveResult;
      if (result.ok) {
        setExchangeMode(false);
        setAiApproved(true);
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
      const result = (await api.pass(token, gameId, 0)) as MoveResult;
      if (result.ok) {
        setAiApproved(true);
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

  const isMyTurn = gameState?.current_turn_slot === 0;
  const isAITurn = gameState?.current_turn_slot === 1 && !gameState?.game_over;
  const showAIPrompt = isAITurn && !aiApproved && !aiThinking;

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
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <div className="min-h-screen bg-gradient-to-br from-stone-950 via-stone-900 to-stone-950 text-stone-100">
        <div className="max-w-2xl mx-auto px-4 py-4 flex flex-col gap-3">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="text-xs text-stone-500 font-mono">{selectedModelId}</div>
            <button
              onClick={() => router.push("/settings")}
              className="p-2 rounded-lg hover:bg-stone-800 transition-colors text-stone-400 hover:text-stone-200"
              title="Settings"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"
                fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </button>
          </div>

          <ScorePanel />
          <Board />
          <TileRack />

          {/* AI Turn prompt */}
          <AnimatePresence>
            {showAIPrompt && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="flex flex-col items-center gap-3 p-4 bg-stone-800/60 backdrop-blur-sm rounded-xl border border-stone-700/40"
              >
                <p className="text-stone-300 text-sm text-center">
                  AI&apos;s turn — ready when you are
                </p>
                <div className="flex gap-3">
                  <button onClick={() => router.push("/settings")}
                    className="px-4 py-2.5 rounded-xl bg-stone-700/60 text-stone-300 text-sm
                      font-medium hover:bg-stone-700 transition-colors border border-stone-600/30">
                    Settings
                  </button>
                  <button onClick={() => setAiApproved(true)}
                    className="px-6 py-2.5 rounded-xl bg-emerald-600 text-white text-sm
                      font-bold hover:bg-emerald-500 transition-all shadow-lg shadow-emerald-600/20
                      hover:shadow-emerald-500/30 active:scale-95">
                    Let AI Play
                  </button>
                </div>
                {aiError && (
                  <p className="text-red-400/80 text-xs text-center max-w-xs mt-1">
                    Last error: {aiError}
                  </p>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Human controls */}
          {isMyTurn && (
            <div className="flex justify-center">
              <GameControls onPlay={handlePlay} onExchange={handleExchange} onPass={handlePass}
                disabled={!isMyTurn || gameState?.game_over} />
            </div>
          )}

          {/* Game over */}
          <AnimatePresence>
            {gameState?.game_over && (
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                className="text-center p-6 bg-stone-800/80 backdrop-blur rounded-xl">
                <h2 className="text-3xl font-bold mb-2">
                  {gameState.winner_slot === 0 ? "Victory!" : gameState.winner_slot === 1 ? "Game Over" : "Draw!"}
                </h2>
                <p className="text-stone-400 mb-4">
                  {gameState.slots.map((s) => `${s.username}: ${s.score}`).join(" vs ")}
                </p>
                <button onClick={() => router.push("/")}
                  className="px-6 py-3 rounded-xl bg-amber-500 text-stone-900 font-semibold hover:bg-amber-400 transition-colors">
                  New Game
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      <AIThinkingOverlay />
      <BlankPicker onSelect={handleBlankSelect} />

      {/* Toast overlays */}
      <AnimatePresence>
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
