"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { useGameStore } from "@/hooks/useGameStore";
import {
  PREMIUM_GOLD_TEXT_SHADOW_CLASS,
  PREMIUM_HEADER_STYLE,
  PREMIUM_PANEL_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";

export default function Home() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const setToken = useGameStore((s) => s.setToken);
  const selectedModelId = useGameStore((s) => s.selectedModelId);
  const setSelectedModelId = useGameStore((s) => s.setSelectedModelId);
  const setCreditBalance = useGameStore((s) => s.setCreditBalance);
  const resetGameUi = useGameStore((s) => s.resetGameUi);
  const premiumLookEnabled = useGameStore((s) => s.premiumLookEnabled);
  const premiumTitleClass = premiumLookEnabled ? PREMIUM_GOLD_TEXT_SHADOW_CLASS : "";

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

      resetGameUi();
      router.push("/play");
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
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(214,169,78,0.16),transparent_24%),linear-gradient(180deg,#0d0b09,#060505)] text-stone-100">
      <div className="mx-auto flex min-h-screen max-w-[1120px] items-center justify-center p-4 sm:p-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="grid w-full max-w-[980px] gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(360px,420px)]"
        >
          <div
            className={`relative overflow-hidden rounded-[2.2rem] border border-white/10 px-6 py-7 shadow-[0_32px_80px_rgba(0,0,0,0.42)] ${premiumLookEnabled ? "backdrop-blur-[16px]" : "bg-black/55"}`}
            style={premiumLookEnabled ? PREMIUM_HEADER_STYLE : undefined}
            onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
          >
            <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/58 to-transparent" />
            <div className="text-[0.78rem] uppercase tracking-[0.36em] text-stone-500">
              Libre Tiles
            </div>
            <h1 className={`mt-4 font-gold-shiny text-5xl font-black tracking-tight sm:text-6xl ${premiumTitleClass}`}>
              Premium Libre Tiles,
              <br />
              human and AI.
            </h1>
            <p className="mt-4 max-w-[34rem] text-base text-stone-300 sm:text-lg">
              Open-source wordplay with live matchmaking, sharp AI rivals, premium board chrome, and a history surface ready for your next board.
            </p>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {[
                ["🤖", "AI duels", "Model-aware premium games"],
                ["🤝", "Live queue", "Realtime sync and chat"],
                ["🗂️", "Saved boards", "Resume AI or human games"],
              ].map(([emoji, title, body]) => (
                <div
                  key={title}
                  className={`rounded-[1.4rem] border border-white/8 px-4 py-4 ${premiumLookEnabled ? "backdrop-blur-[12px]" : "bg-black/20"}`}
                  style={premiumLookEnabled ? PREMIUM_PANEL_STYLE : undefined}
                  onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
                >
                  <div className="text-[1.15rem] leading-none">{emoji}</div>
                  <div className={`mt-3 font-gold-shiny text-[1.12rem] font-black leading-none ${premiumTitleClass}`}>
                    {title}
                  </div>
                  <div className="mt-2 text-sm text-stone-300">
                    {body}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div
            className={`relative overflow-hidden rounded-[2rem] border border-white/10 p-6 shadow-[0_28px_72px_rgba(0,0,0,0.42)] ${premiumLookEnabled ? "backdrop-blur-[16px]" : "bg-stone-800/60 backdrop-blur-md"}`}
            style={premiumLookEnabled ? PREMIUM_PANEL_STYLE : undefined}
            onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
          >
            <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/54 to-transparent" />
            <div className="mb-5">
              <div className="text-[0.72rem] uppercase tracking-[0.3em] text-stone-500">
                Account
              </div>
              <div className={`mt-2 font-gold-shiny text-[2rem] font-black leading-none ${premiumTitleClass}`}>
                {mode === "login" ? "Sign in" : "Create account"}
              </div>
            </div>

            <div className="mb-5 flex gap-2">
              <button
                onClick={() => setMode("login")}
                className={`flex-1 rounded-xl py-2.5 text-sm font-medium transition-colors ${
                  mode === "login"
                    ? "border border-amber-300/24 bg-amber-500/14 text-amber-200"
                    : "border border-transparent text-stone-400 hover:text-stone-200"
                }`}
              >
                Sign In
              </button>
              <button
                onClick={() => setMode("register")}
                className={`flex-1 rounded-xl py-2.5 text-sm font-medium transition-colors ${
                  mode === "register"
                    ? "border border-amber-300/24 bg-amber-500/14 text-amber-200"
                    : "border border-transparent text-stone-400 hover:text-stone-200"
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
                className="w-full rounded-xl border border-stone-700/50 bg-stone-950/46 px-4 py-3 text-stone-100 placeholder-stone-500 outline-none transition focus:border-amber-300/40 focus:ring-2 focus:ring-amber-500/20"
              />
              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-stone-700/50 bg-stone-950/46 px-4 py-3 text-stone-100 placeholder-stone-500 outline-none transition focus:border-amber-300/40 focus:ring-2 focus:ring-amber-500/20"
              />
            </div>

            {error && (
              <p className="mt-3 text-sm text-rose-400">{error}</p>
            )}

            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleAuth}
              disabled={loading || !username || !password}
              className={`group mt-5 w-full rounded-xl border border-amber-200/30 py-3.5 shadow-[0_16px_36px_rgba(251,191,36,0.12)] transition-all disabled:cursor-not-allowed disabled:opacity-40 ${premiumLookEnabled ? "backdrop-blur-[10px]" : "bg-gradient-to-r from-amber-400 to-amber-500"} ${premiumLookEnabled ? "" : "text-stone-900"}`}
              style={premiumLookEnabled ? PREMIUM_PANEL_STYLE : undefined}
              onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
            >
              <span className={`font-gold-shiny text-[1.08rem] font-black leading-none ${premiumTitleClass}`}>
                {loading ? "Signing in..." : mode === "login" ? "Play now" : "Create account & play"}
              </span>
            </motion.button>

            <p className="mt-5 text-center text-xs text-stone-500">
              Open source • Collins Scrabble Words 2019 • 279,496 valid words
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
