"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";

import { useGameStore } from "@/hooks/useGameStore";
import { api } from "@/lib/api";
import type { CreateGameResponse, QueueJoinResponse } from "@/lib/types";

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
  const setStartingDraw = useGameStore((state) => state.setStartingDraw);
  const setStartingRack = useGameStore((state) => state.setStartingRack);
  const setGameState = useGameStore((state) => state.setGameState);
  const resetGameUi = useGameStore((state) => state.resetGameUi);

  const [startingAI, setStartingAI] = useState(false);
  const [joiningHuman, setJoiningHuman] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeModelLabel = humanizeModelId(selectedModelId);

  async function handleStartAI() {
    if (!token || startingAI) {
      if (!token) router.push("/");
      return;
    }

    setStartingAI(true);
    setError(null);
    try {
      const result = (await api.createGame(token, {
        game_mode: "vs_ai",
        ai_model_model_id: selectedModelId || undefined,
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
    if (!token || joiningHuman) {
      if (!token) router.push("/");
      return;
    }

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

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(203,144,49,0.14),transparent_28%),linear-gradient(180deg,#0d0b09,#060505)] text-stone-100">
      <div className="mx-auto flex min-h-screen max-w-[1100px] flex-col justify-center px-4 py-6 sm:px-6">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
          className="mx-auto w-full max-w-[920px]"
        >
          <div className="mb-10 text-center">
            <div className="text-[0.78rem] uppercase tracking-[0.36em] text-stone-500">
              Libre Tiles
            </div>
            <h1 className="mt-3 text-4xl font-black tracking-tight text-stone-50 sm:text-5xl">
              Choose the next board
            </h1>
            <p className="mt-3 text-sm text-stone-400 sm:text-base">
              Start an AI match or enter the human queue.
            </p>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <button
              onClick={() => void handleStartAI()}
              disabled={startingAI || joiningHuman}
              className="group rounded-[2rem] border border-amber-300/20 bg-[linear-gradient(180deg,rgba(52,34,14,0.96),rgba(18,12,9,0.98))] p-7 text-left shadow-[0_26px_60px_rgba(0,0,0,0.32)] transition-all hover:border-white/40 hover:shadow-[0_30px_70px_rgba(255,255,255,0.06)] disabled:opacity-50"
            >
              <div className="text-[0.72rem] uppercase tracking-[0.34em] text-amber-300/70">
                AI Match
              </div>
              <div className="mt-4 text-3xl font-black text-stone-50">
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
              className="group rounded-[2rem] border border-sky-300/18 bg-[linear-gradient(180deg,rgba(9,27,37,0.96),rgba(8,12,17,0.98))] p-7 text-left shadow-[0_26px_60px_rgba(0,0,0,0.32)] transition-all hover:border-white/40 hover:shadow-[0_30px_70px_rgba(255,255,255,0.06)] disabled:opacity-50"
            >
              <div className="text-[0.72rem] uppercase tracking-[0.34em] text-sky-300/72">
                Human Queue
              </div>
              <div className="mt-4 text-3xl font-black text-stone-50">
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

          <div className="mt-5 flex items-center justify-center gap-3 text-sm text-stone-400">
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
            <div className="mt-5 text-center text-sm text-rose-400">
              {error}
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
