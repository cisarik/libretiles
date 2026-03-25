"use client";

import { motion } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";
import {
  PREMIUM_MODAL_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";
import type { AIPrompt } from "@/lib/types";

const MODAL_TRANSITION = {
  duration: 0.24,
  ease: [0.22, 1, 0.36, 1] as const,
};

function promptExcerpt(value: string) {
  return value.replace(/\s+/g, " ").trim().slice(0, 140);
}

export function PromptCatalogModal({
  prompts,
  selectedPromptId,
  loading,
  savingPromptId,
  onClose,
  onSelect,
  onPreview,
}: {
  prompts: AIPrompt[];
  selectedPromptId: number | null | undefined;
  loading: boolean;
  savingPromptId: number | null;
  onClose: () => void;
  onSelect: (prompt: AIPrompt) => void;
  onPreview: (prompt: AIPrompt) => void;
}) {
  const premiumLookEnabled = useGameStore((s) => s.premiumLookEnabled);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={MODAL_TRANSITION}
      className="fixed inset-0 z-[87] flex items-center justify-center bg-black/58 px-3 py-3 backdrop-blur-sm sm:px-4 sm:py-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, y: 28, scale: 0.965 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.985 }}
        transition={MODAL_TRANSITION}
        className={`relative mx-auto flex max-h-[calc(100svh-1.5rem)] w-full max-w-[1040px] flex-col overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(24,20,16,0.96),rgba(11,9,8,0.98))] shadow-[0_30px_100px_rgba(0,0,0,0.5)] ${premiumLookEnabled ? "backdrop-blur-[16px]" : "backdrop-blur-xl"} sm:max-h-[calc(100svh-2rem)] sm:rounded-[2.2rem]`}
        style={premiumLookEnabled ? PREMIUM_MODAL_STYLE : undefined}
        onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="pointer-events-none absolute inset-x-12 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/70 to-transparent" />
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(251,191,36,0.08),transparent_34%)]" />

        <div className="relative border-b border-white/8 px-4 py-4 sm:px-5 sm:py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-3">
                <span className="text-[1.8rem] leading-none sm:text-[2rem]">📝</span>
                <div>
                  <div className="font-gold-shiny text-3xl font-black tracking-tight sm:text-[2.6rem]">
                    Prompts
                  </div>
                  <div className="mt-1 text-sm text-stone-300">
                    Change how the AI searches the board, from safer lines to faster short-word pressure.
                  </div>
                </div>
              </div>
            </div>

            <motion.button
              type="button"
              whileHover={{ y: -1.5 }}
              whileTap={{ scale: 0.985 }}
              onClick={onClose}
              className="rounded-full border border-white/10 bg-white/6 px-4 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-white/18 hover:bg-white/8"
            >
              <span className="font-gold-shiny text-[1rem] font-black leading-none sm:text-[1.08rem]">
                Close
              </span>
            </motion.button>
          </div>
        </div>

        <div className="ornate-scrollbar relative flex-1 overflow-y-auto p-4 sm:p-5">
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, index) => (
                <div
                  key={index}
                  className="animate-pulse rounded-[1.35rem] border border-white/8 bg-white/[0.03] px-4 py-4"
                >
                  <div className="h-5 w-44 rounded-full bg-white/10" />
                  <div className="mt-3 h-4 w-full rounded-full bg-white/8" />
                  <div className="mt-2 h-4 w-2/3 rounded-full bg-white/6" />
                </div>
              ))}
            </div>
          ) : prompts.length > 0 ? (
            <div
              className="relative overflow-hidden rounded-[1.85rem] border border-white/8 shadow-[0_18px_45px_rgba(0,0,0,0.24)]"
              style={premiumLookEnabled ? PREMIUM_MODAL_STYLE : undefined}
              onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
            >
              <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/12 to-transparent" />
              <div className="ornate-scrollbar overflow-x-auto">
                <table className="min-w-[760px] w-full border-separate border-spacing-0">
                  <thead className="sticky top-0 z-10 backdrop-blur-xl">
                    <tr className="bg-[linear-gradient(180deg,rgba(22,19,16,0.98),rgba(15,12,10,0.94))] text-left">
                      <th className="border-b border-white/8 px-4 py-3 text-[0.78rem] uppercase tracking-[0.24em] text-stone-400">
                        Prompt
                      </th>
                      <th className="border-b border-white/8 px-4 py-3 text-right text-[0.78rem] uppercase tracking-[0.24em] text-stone-400">
                        Fitness
                      </th>
                      <th className="border-b border-white/8 px-4 py-3 text-right text-[0.78rem] uppercase tracking-[0.24em] text-stone-400">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {prompts.map((prompt) => {
                      const isSelected = selectedPromptId === prompt.id;
                      const isSaving = savingPromptId === prompt.id;
                      return (
                        <tr
                          key={prompt.id}
                          className={`group transition-[background-color] duration-300 ${
                            isSelected
                              ? "bg-[linear-gradient(90deg,rgba(251,191,36,0.12),rgba(251,191,36,0.03)_42%,transparent)]"
                              : "hover:bg-white/[0.035]"
                          }`}
                        >
                          <td
                            className={`rounded-l-[1.35rem] px-4 py-5 align-top ${
                              isSelected
                                ? "border-y border-l border-amber-300/44 shadow-[inset_0_0_0_1px_rgba(251,191,36,0.18)]"
                                : "border-b border-white/6 group-hover:border-amber-300/14"
                            }`}
                          >
                            <div className="flex items-start gap-3">
                              <div className={`mt-0.5 flex h-12 w-12 shrink-0 items-center justify-center rounded-[1rem] border text-[1.6rem] ${
                                isSelected
                                  ? "border-amber-300/28 bg-amber-200/8"
                                  : "border-white/10 bg-stone-950/78"
                              }`}>
                                🧠
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <div className="truncate text-[1.22rem] font-black sm:text-[1.3rem]">
                                    <span className={isSelected ? "font-gold-shiny" : "font-gold-dark"}>
                                      {prompt.name}
                                    </span>
                                  </div>
                                  {isSelected ? (
                                    <span className="rounded-full border border-amber-300/20 bg-amber-400/12 px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-amber-100">
                                      Active
                                    </span>
                                  ) : null}
                                  {isSaving ? (
                                    <span className="rounded-full border border-sky-300/18 bg-sky-400/10 px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-sky-100">
                                      Saving
                                    </span>
                                  ) : null}
                                </div>
                                <div className="mt-2 text-sm leading-6 text-stone-300">
                                  {promptExcerpt(prompt.prompt)}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td
                            className={`px-4 py-5 text-right align-top ${
                              isSelected
                                ? "border-y border-amber-300/44 shadow-[inset_0_0_0_1px_rgba(251,191,36,0.18)]"
                                : "border-b border-white/6 group-hover:border-amber-300/14"
                            }`}
                          >
                            <div className="inline-flex rounded-full border border-white/10 bg-white/[0.05] px-3 py-1.5 text-[0.9rem] font-semibold text-stone-100">
                              {Number.isFinite(prompt.fitness) ? prompt.fitness.toFixed(2) : "0.00"}
                            </div>
                          </td>
                          <td
                            className={`rounded-r-[1.35rem] px-4 py-5 text-right align-top ${
                              isSelected
                                ? "border-y border-r border-amber-300/44 shadow-[inset_0_0_0_1px_rgba(251,191,36,0.18)]"
                                : "border-b border-white/6 group-hover:border-amber-300/14"
                            }`}
                          >
                            <div className="flex justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => onPreview(prompt)}
                                className="rounded-full border border-white/10 bg-white/6 px-3.5 py-2 text-[0.92rem] font-black text-stone-100 transition-all duration-200 hover:border-white/18 hover:bg-white/8"
                              >
                                Preview
                              </button>
                              <button
                                type="button"
                                onClick={() => onSelect(prompt)}
                                disabled={isSaving}
                                className={`rounded-full border px-3.5 py-2 text-[0.92rem] font-black transition-all duration-200 ${
                                  isSelected
                                    ? "border-amber-300/24 bg-amber-400/12 text-amber-100"
                                    : "border-amber-300/18 bg-[linear-gradient(145deg,rgba(31,23,16,0.86),rgba(13,10,8,0.92))] text-amber-100 hover:border-white/30 hover:bg-[linear-gradient(145deg,rgba(78,64,46,0.96),rgba(26,21,16,0.98))]"
                                } disabled:cursor-not-allowed disabled:opacity-50`}
                              >
                                {isSelected ? "Selected" : "Use prompt"}
                              </button>
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
            <div className="rounded-[1.6rem] border border-white/8 bg-white/[0.03] px-5 py-10 text-center shadow-[0_16px_40px_rgba(0,0,0,0.22)]">
              <div className="font-gold-shiny text-[1.6rem] font-black text-stone-50 sm:text-[1.9rem]">
                No prompt presets yet
              </div>
              <div className="mt-2 text-sm leading-6 text-stone-300">
                Add prompts in the database and they will appear here immediately.
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
