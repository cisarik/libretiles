"use client";

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";
import { useT } from "@/lib/i18n";

const ENGLISH_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

interface BlankPickerProps {
  onSelect: (letter: string) => void;
}

export function BlankPicker({ onSelect }: BlankPickerProps) {
  const isOpen = useGameStore((s) => s.blankPickerOpen);
  const closeBlankPicker = useGameStore((s) => s.closeBlankPicker);
  const alphabet = useGameStore((s) => s.gameState?.alphabet);
  const { t } = useT();
  const dialogRef = useRef<HTMLDivElement>(null);
  const letters =
    alphabet && alphabet.length > 0
      ? alphabet.filter((letter) => letter !== "?")
      : ENGLISH_LETTERS;

  useEffect(() => {
    if (!isOpen) return;
    dialogRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") closeBlankPicker();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeBlankPicker, isOpen]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={closeBlankPicker}
        >
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="blank-picker-dialog-title"
            tabIndex={-1}
            initial={{ scale: 0.8, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.8, y: 20 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            onClick={(e) => e.stopPropagation()}
            className="max-w-[min(92vw,28rem)] bg-stone-800/95 backdrop-blur-md rounded-2xl p-6 shadow-2xl shadow-black/50 border border-stone-700/50"
          >
            <h3 id="blank-picker-dialog-title" className="text-center text-stone-300 font-semibold mb-4">
              {t("blank.chooseLetter")}
            </h3>
            <div className="grid grid-cols-7 gap-1.5 sm:gap-2">
              {letters.map((letter) => (
                <motion.button
                  key={letter}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={() => {
                    onSelect(letter);
                    closeBlankPicker();
                  }}
                  className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50 text-sm font-bold text-stone-800
                    shadow-md hover:shadow-lg hover:bg-amber-100 transition-colors sm:h-9 sm:w-9 sm:text-base"
                >
                  {letter}
                </motion.button>
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
