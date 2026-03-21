"use client";

import { useMemo } from "react";
import { useDraggable } from "@dnd-kit/core";
import { motion, AnimatePresence } from "framer-motion";
import { Tile } from "./Tile";
import { useGameStore } from "@/hooks/useGameStore";
import { isPlausibleRack } from "@/lib/rack";

function DraggableTile({
  letter,
  index,
  isExchangeMode,
  isSelected,
  onSelect,
}: {
  letter: string;
  index: number;
  isExchangeMode: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `rack-${index}`,
    data: { letter, index, origin: "rack" },
    disabled: isExchangeMode,
  });

  return (
    <motion.div
      ref={setNodeRef}
      {...(isExchangeMode ? {} : { ...listeners, ...attributes })}
      layout="position"
      initial={{ scale: 0, y: 20 }}
      animate={{ scale: 1, y: 0 }}
      exit={{ scale: 0, y: -20 }}
      transition={{
        layout: { duration: 0.16, ease: [0.22, 1, 0.36, 1] },
        duration: 0.18,
        ease: [0.22, 1, 0.36, 1],
        delay: index * 0.03,
      }}
      onClick={isExchangeMode ? onSelect : undefined}
      className={`will-change-transform ${isDragging ? "opacity-0" : ""}`}
      style={{ touchAction: isExchangeMode ? "auto" : "none" }}
    >
      <Tile
        letter={letter}
        isSelected={isSelected}
        isDragging={isDragging}
        size="lg"
        hoverable={false}
      />
    </motion.div>
  );
}

export function TileRack() {
  const gameState = useGameStore((s) => s.gameState);
  const startingRack = useGameStore((s) => s.startingRack);
  const exchangeMode = useGameStore((s) => s.exchangeMode);
  const exchangeSelected = useGameStore((s) => s.exchangeSelected);
  const toggleExchangeSelection = useGameStore((s) => s.toggleExchangeSelection);
  const pendingTiles = useGameStore((s) => s.pendingTiles);

  const fullRack = useMemo(() => {
    if (isPlausibleRack(gameState?.my_rack)) {
      return gameState.my_rack;
    }
    if (isPlausibleRack(startingRack)) {
      return startingRack;
    }
    return [];
  }, [gameState?.my_rack, startingRack]);

  const usedIndices = new Set(pendingTiles.map((t) => t.rackIndex));
  const visibleRack = fullRack
    .map((letter, i) => ({ letter, index: i }))
    .filter(({ index }) => !usedIndices.has(index));

  return (
    <div className="flex items-center justify-center gap-2 rounded-[1.4rem] border border-white/8 bg-stone-900/72 p-3.5 shadow-[0_20px_48px_rgba(0,0,0,0.28)] backdrop-blur-sm sm:gap-2.5 sm:p-4">
      <AnimatePresence mode="popLayout">
        {visibleRack.map(({ letter, index }) => (
          <DraggableTile
            key={`${index}-${letter}`}
            letter={letter}
            index={index}
            isExchangeMode={exchangeMode}
            isSelected={exchangeSelected.has(index)}
            onSelect={() => toggleExchangeSelection(index)}
          />
        ))}
      </AnimatePresence>
      {visibleRack.length === 0 && (
        <span className="text-stone-500 text-sm italic">No tiles on rack</span>
      )}
    </div>
  );
}
