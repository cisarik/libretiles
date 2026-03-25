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

export function PromptPreviewModal({
  prompt,
  selected = false,
  saving = false,
  onSelect,
  onClose,
}: {
  prompt: AIPrompt;
  selected?: boolean;
  saving?: boolean;
  onSelect?: (prompt: AIPrompt) => void;
  onClose: () => void;
}) {
  const premiumLookEnabled = useGameStore((s) => s.premiumLookEnabled);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={MODAL_TRANSITION}
      className="fixed inset-0 z-[88] flex items-center justify-center bg-black/62 px-3 py-3 backdrop-blur-sm sm:px-4 sm:py-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, y: 28, scale: 0.965 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.985 }}
        transition={MODAL_TRANSITION}
        className={`relative mx-auto flex max-h-[calc(100svh-1.5rem)] w-full max-w-[980px] flex-col overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(24,20,16,0.96),rgba(11,9,8,0.98))] shadow-[0_30px_100px_rgba(0,0,0,0.5)] ${premiumLookEnabled ? "backdrop-blur-[16px]" : "backdrop-blur-xl"} sm:max-h-[calc(100svh-2rem)] sm:rounded-[2.2rem]`}
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
                <span className="text-[1.8rem] leading-none sm:text-[2rem]">📜</span>
                <div>
                  <div className="font-gold-shiny text-3xl font-black tracking-tight sm:text-[2.6rem]">
                    {prompt.name}
                  </div>
                  <div className="mt-1 text-sm text-stone-300">
                    Fitness {Number.isFinite(prompt.fitness) ? prompt.fitness.toFixed(2) : "0.00"}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap justify-end gap-2">
              {onSelect ? (
                <motion.button
                  type="button"
                  whileHover={{ y: -1.5 }}
                  whileTap={{ scale: 0.985 }}
                  onClick={() => onSelect(prompt)}
                  disabled={saving}
                  className={`rounded-full border px-4 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18)] transition-[border-color,box-shadow,background-color,transform] duration-300 disabled:cursor-not-allowed disabled:opacity-50 ${
                    selected
                      ? "border-amber-300/24 bg-amber-400/12"
                      : "border-amber-300/22 bg-[linear-gradient(145deg,rgba(50,36,22,0.96),rgba(15,11,8,0.98))] hover:border-amber-100/52 hover:bg-[linear-gradient(145deg,rgba(97,76,48,0.98),rgba(29,22,16,0.99))]"
                  }`}
                >
                  <span className="font-gold-shiny text-[1rem] font-black leading-none sm:text-[1.08rem]">
                    {saving ? "Saving..." : selected ? "Selected" : "Use prompt"}
                  </span>
                </motion.button>
              ) : null}
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
        </div>

        <div className="ornate-scrollbar relative flex-1 overflow-y-auto p-4 sm:p-5">
          <div
            className="rounded-[1.6rem] border border-white/8 bg-black/18 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.22)]"
            style={premiumLookEnabled ? PREMIUM_MODAL_STYLE : undefined}
            onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
          >
            <pre className="whitespace-pre-wrap break-words font-mono text-[0.92rem] leading-7 text-stone-100 sm:text-[0.98rem]">
              {prompt.prompt}
            </pre>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
