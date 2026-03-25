"use client";

import { AnimatePresence, motion } from "framer-motion";

export function TurnStatusNotice({
  text,
  tone = "neutral",
}: {
  text?: string | null;
  tone?: "active" | "waiting" | "neutral";
}) {
  if (!text) return null;

  const palette =
    tone === "active"
      ? "border-emerald-300/18 bg-emerald-400/10 text-emerald-50"
      : tone === "waiting"
        ? "border-sky-300/16 bg-sky-400/10 text-sky-50"
        : "border-white/10 bg-white/6 text-stone-200";

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={text}
        initial={{ opacity: 0, y: 8, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -8, scale: 0.97 }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        className={`inline-flex min-h-[2.5rem] items-center justify-center gap-2 rounded-full border px-4 py-2 text-center text-[1.12rem] font-black tracking-[0.01em] shadow-[0_14px_30px_rgba(0,0,0,0.24)] sm:min-h-[2.75rem] sm:px-5 sm:text-[1.34rem] ${palette}`}
      >
        <span className="h-2 w-2 rounded-full bg-current opacity-85" />
        <span>{text}</span>
      </motion.div>
    </AnimatePresence>
  );
}
