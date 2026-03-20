"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

interface BlankPickerProps {
  onSelect: (letter: string) => void;
}

export function BlankPicker({ onSelect }: BlankPickerProps) {
  const isOpen = useGameStore((s) => s.blankPickerOpen);
  const closeBlankPicker = useGameStore((s) => s.closeBlankPicker);

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
            initial={{ scale: 0.8, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.8, y: 20 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            onClick={(e) => e.stopPropagation()}
            className="bg-stone-800/95 backdrop-blur-md rounded-2xl p-6 shadow-2xl shadow-black/50 border border-stone-700/50"
          >
            <h3 className="text-center text-stone-300 font-semibold mb-4">
              Choose a letter for blank tile
            </h3>
            <div className="grid grid-cols-7 gap-2">
              {LETTERS.map((letter) => (
                <motion.button
                  key={letter}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={() => {
                    onSelect(letter);
                    closeBlankPicker();
                  }}
                  className="w-10 h-10 rounded-lg bg-amber-50 text-stone-800 font-bold text-lg
                    shadow-md hover:shadow-lg hover:bg-amber-100 transition-colors"
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
