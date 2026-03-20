"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";
import type { AIModel } from "@/lib/types";

const PROVIDER_ICONS: Record<string, string> = {
  openai: "🤖",
  google: "🔮",
  anthropic: "🧠",
  openrouter: "🌐",
  novita: "⚡",
};

const QUALITY_COLORS: Record<string, string> = {
  basic: "bg-stone-600 text-stone-200",
  standard: "bg-sky-600 text-white",
  premium: "bg-amber-500 text-stone-900",
  elite: "bg-purple-600 text-white",
};

const TIMEOUT_CHOICES = [
  { value: 30, label: "30s", description: "Recommended — quick and sharp" },
  { value: 60, label: "1 min", description: "Balanced" },
  { value: 120, label: "2 min", description: "Thorough" },
  { value: 180, label: "3 min", description: "Deep search" },
  { value: 300, label: "5 min", description: "Maximum — tournament mode" },
];

export default function SettingsPage() {
  const router = useRouter();
  const selectedModelId = useGameStore((s) => s.selectedModelId);
  const setSelectedModelId = useGameStore((s) => s.setSelectedModelId);
  const aiTimeout = useGameStore((s) => s.aiTimeout);
  const setAITimeout = useGameStore((s) => s.setAITimeout);

  const [models, setModels] = useState<AIModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [customModel, setCustomModel] = useState("");

  useEffect(() => {
    fetch("/api/models")
      .then((r) => r.json())
      .then((data) => {
        setModels(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleSelect = (modelId: string) => {
    setSelectedModelId(modelId);
  };

  const handleCustomApply = () => {
    if (customModel.includes("/")) {
      setSelectedModelId(customModel);
      setCustomModel("");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-950 via-stone-900 to-stone-950 text-stone-100">
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Settings</h1>
          <button
            onClick={() => router.back()}
            className="px-4 py-2 rounded-lg bg-stone-800 hover:bg-stone-700 text-sm transition-colors"
          >
            Back to game
          </button>
        </div>

        {/* Model Selection */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-1">AI Opponent</h2>
          <p className="text-stone-400 text-sm mb-4">
            Choose which AI model to play against. Models are routed through{" "}
            <a
              href="https://vercel.com/docs/ai-gateway"
              target="_blank"
              className="text-amber-400 hover:underline"
            >
              Vercel AI Gateway
            </a>
            .
          </p>

          <div className="text-xs text-stone-500 mb-3">
            Current: <span className="text-amber-300 font-mono">{selectedModelId}</span>
          </div>

          {loading ? (
            <div className="text-stone-500 text-sm animate-pulse">
              Loading models...
            </div>
          ) : models.length > 0 ? (
            <div className="grid gap-3">
              <AnimatePresence>
                {models.map((model) => (
                  <motion.button
                    key={model.model_id}
                    layout
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                    onClick={() => handleSelect(model.model_id)}
                    className={`w-full text-left p-4 rounded-xl border transition-all ${
                      selectedModelId === model.model_id
                        ? "border-amber-400/50 bg-amber-500/10 shadow-lg shadow-amber-500/10"
                        : "border-stone-700/50 bg-stone-800/40 hover:border-stone-600"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">
                        {PROVIDER_ICONS[model.provider] || "🔧"}
                      </span>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">{model.display_name}</span>
                          <span
                            className={`text-[0.6rem] px-1.5 py-0.5 rounded-full font-medium uppercase ${
                              QUALITY_COLORS[model.quality_tier] || QUALITY_COLORS.standard
                            }`}
                          >
                            {model.quality_tier}
                          </span>
                        </div>
                        <div className="text-xs text-stone-400 mt-0.5 font-mono">
                          {model.model_id}
                        </div>
                        {model.description && (
                          <div className="text-xs text-stone-500 mt-1">
                            {model.description}
                          </div>
                        )}
                      </div>
                      <div className="text-right">
                        {Number(model.cost_per_game) > 0 && (
                          <div className="text-sm font-medium text-amber-300">
                            {model.cost_per_game} cr
                          </div>
                        )}
                        {selectedModelId === model.model_id && (
                          <div className="text-xs text-emerald-400 mt-1">
                            Selected
                          </div>
                        )}
                      </div>
                    </div>
                  </motion.button>
                ))}
              </AnimatePresence>
            </div>
          ) : (
            <div className="text-stone-500 text-sm p-4 bg-stone-800/40 rounded-xl border border-stone-700/50">
              No models configured in admin yet. Using custom model input below,
              or add models at{" "}
              <code className="text-amber-300">/admin/catalog/aimodel/</code>.
            </div>
          )}

          {/* Custom model input */}
          <div className="mt-4 p-4 bg-stone-800/40 rounded-xl border border-stone-700/50">
            <label className="text-sm text-stone-400 block mb-2">
              Custom model (provider/model format)
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={customModel}
                onChange={(e) => setCustomModel(e.target.value)}
                placeholder="openai/gpt-4o-mini"
                className="flex-1 px-3 py-2 bg-stone-900/50 border border-stone-700/50 rounded-lg
                  text-stone-100 text-sm placeholder-stone-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 font-mono"
              />
              <button
                onClick={handleCustomApply}
                disabled={!customModel.includes("/")}
                className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-sm font-medium
                  disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Apply
              </button>
            </div>
            <p className="text-xs text-stone-500 mt-2">
              Examples: openai/gpt-4o, openai/gpt-5.2, anthropic/claude-sonnet-4.6,
              google/gemini-2.5-pro
            </p>
          </div>
        </section>

        {/* AI Timeout */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-1">AI Thinking Time</h2>
          <p className="text-stone-400 text-sm mb-4">
            How long the AI agent has to search for the best move. Longer time
            means more candidates explored and potentially better play.
          </p>

          <div className="grid grid-cols-5 gap-2">
            {TIMEOUT_CHOICES.map((choice) => (
              <motion.button
                key={choice.value}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => setAITimeout(choice.value)}
                className={`flex flex-col items-center gap-1 p-3 rounded-xl border transition-all ${
                  aiTimeout === choice.value
                    ? "border-amber-400/50 bg-amber-500/10 shadow-lg shadow-amber-500/10"
                    : "border-stone-700/50 bg-stone-800/40 hover:border-stone-600"
                }`}
              >
                <span
                  className={`text-lg font-bold ${
                    aiTimeout === choice.value
                      ? "text-amber-300"
                      : "text-stone-300"
                  }`}
                >
                  {choice.label}
                </span>
                <span className="text-[0.6rem] text-stone-500 text-center leading-tight">
                  {choice.description}
                </span>
              </motion.button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
