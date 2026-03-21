"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { useGameStore } from "@/hooks/useGameStore";
import type { CreateGameResponse } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const setToken = useGameStore((s) => s.setToken);
  const setStartingDraw = useGameStore((s) => s.setStartingDraw);
  const setStartingRack = useGameStore((s) => s.setStartingRack);
  const selectedModelId = useGameStore((s) => s.selectedModelId);
  const setSelectedModelId = useGameStore((s) => s.setSelectedModelId);
  const setCreditBalance = useGameStore((s) => s.setCreditBalance);
  const resetGameUi = useGameStore((s) => s.resetGameUi);

  const handleAuth = async () => {
    setError("");
    setLoading(true);
    try {
      if (mode === "register") {
        try {
          await api.register({ username, email: `${username}@libretiles.app`, password });
        } catch {
          // User may already exist — fall through to login
        }
      }
      const { access } = await api.login({ username, password });
      setToken(access);
      const profile = await api.me(access);
      setCreditBalance(profile.credit_balance);

      const models = await api.getModels();
      const fallbackModelId = models[0]?.model_id ?? null;
      const preferredModelId = profile.preferred_ai_model_id || selectedModelId;
      const resolvedSelection = models.some((model) => model.model_id === preferredModelId)
        ? preferredModelId
        : fallbackModelId;

      if (!resolvedSelection) {
        throw new Error("No active AI models are available.");
      }

      if (resolvedSelection !== selectedModelId) {
        setSelectedModelId(resolvedSelection);
      }

      const result = (await api.createGame(access, {
        game_mode: "vs_ai",
        ai_model_model_id: resolvedSelection,
      })) as CreateGameResponse;
      if (result.ai_model_id) {
        setSelectedModelId(result.ai_model_id);
      }
      resetGameUi();
      setStartingDraw(result.starting_draw);
      setStartingRack(result.human_rack);
      router.push(`/draw/${result.game_id}`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message.includes("401")
            ? "Invalid username or password"
            : err.message
          : "Something went wrong",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-950 via-stone-900 to-stone-950 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="w-full max-w-md"
      >
        <div className="text-center mb-8">
          <motion.h1
            initial={{ scale: 0.9 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 200 }}
            className="text-5xl font-bold bg-gradient-to-r from-amber-200 to-amber-400 bg-clip-text text-transparent"
          >
            Libre Tiles
          </motion.h1>
          <p className="text-stone-400 mt-2">
            Open-source Scrabble with AI opponents
          </p>
        </div>

        <div className="bg-stone-800/60 backdrop-blur-md rounded-2xl p-6 shadow-2xl shadow-black/40 border border-stone-700/50">
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setMode("login")}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === "login"
                  ? "bg-amber-500/20 text-amber-300"
                  : "text-stone-400 hover:text-stone-200"
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => setMode("register")}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === "register"
                  ? "bg-amber-500/20 text-amber-300"
                  : "text-stone-400 hover:text-stone-200"
              }`}
            >
              Register
            </button>
          </div>

          <div className="space-y-3">
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-3 bg-stone-900/50 border border-stone-700/50 rounded-xl
                text-stone-100 placeholder-stone-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 bg-stone-900/50 border border-stone-700/50 rounded-xl
                text-stone-100 placeholder-stone-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
            />
          </div>

          {error && (
            <p className="text-rose-400 text-sm mt-3">{error}</p>
          )}

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleAuth}
            disabled={loading || !username || !password}
            className="w-full mt-4 py-3 rounded-xl font-semibold text-stone-900
              bg-gradient-to-r from-amber-400 to-amber-500 shadow-lg shadow-amber-500/20
              hover:from-amber-300 hover:to-amber-400
              disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            {loading ? "Starting game..." : mode === "login" ? "Play Now" : "Create Account & Play"}
          </motion.button>
        </div>

        <p className="text-center text-stone-600 text-xs mt-6">
          Open source • Collins Scrabble Words 2019 • 279,496 valid words
        </p>
      </motion.div>
    </div>
  );
}
